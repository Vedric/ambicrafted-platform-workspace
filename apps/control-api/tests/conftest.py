"""Isolated control-plane fixtures: temporary private state, no network or models."""

import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from plateforme.config import Parametres, enregistrer_secret
from plateforme.depot import Depot
from plateforme.moteur import Moteur
from plateforme.services import Services


@pytest.fixture(autouse=True)
def reseau_interdit(monkeypatch):
    original = socket.socket.connect

    def connecter(sock, adresse):
        if sock.family == socket.AF_UNIX:
            return original(sock, adresse)
        raise AssertionError("Aucun réseau externe n'est autorisé dans ces tests.")

    monkeypatch.setattr(socket.socket, "connect", connecter)


@pytest.fixture
def parametres(tmp_path: Path) -> Parametres:
    racine = tmp_path / "depot"
    racine.mkdir(mode=0o700)
    (racine / "runbooks").mkdir()
    (racine / "runbooks/postgres.md").write_text(
        "# PostgreSQL indisponible\n\nVérifier le service avant toute action.\n", encoding="utf-8"
    )
    web = racine / "apps/console/dist"
    web.mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><title>Console locale</title>")
    (web / "asset.js").write_text("export const locale = true;")
    return Parametres(racine=racine, etat=tmp_path / "etat", cle=secrets.token_urlsafe(48))


@pytest.fixture
def depot(parametres):
    return Depot(parametres.etat)


@pytest.fixture
def moteur(parametres, depot):
    return Moteur(parametres, depot)


class MoteurSansExecution(Moteur):
    """Keep real queue/state transitions, replacing only the subprocess consumer."""

    async def demarrer(self):
        self.depot.reprendre_apres_arret()


@pytest.fixture
def application(parametres, monkeypatch):
    from plateforme.app import creer_app

    async def sante(_):
        return {"services": [], "modeles": [], "index": {}, "ok": True}

    async def cibles(_):
        return []

    async def semantique(_, requete):
        return [{"score": 0.7, "donnees": {"texte": requete, "source": "postgres.md"}}]

    monkeypatch.setattr(Services, "sante", sante)
    monkeypatch.setattr(Services, "cibles", cibles)
    monkeypatch.setattr(Services, "semantique", semantique)
    return creer_app(parametres, moteur_classe=MoteurSansExecution)


@pytest.fixture
def client(application, parametres):
    with TestClient(application, base_url=parametres.url) as resultat:
        yield resultat


@pytest.fixture
def bearer(parametres):
    return {"Authorization": "Bearer " + parametres.cle}


@pytest.fixture
def session(client, parametres, bearer):
    ticket = client.post("/api/auth/ticket", headers=bearer, json={}).json()["ticket"]
    reponse = client.post(
        "/api/auth/connexion", json={"ticket": ticket}, headers={"Origin": parametres.url}
    )
    assert reponse.status_code == 200
    return {"Origin": parametres.url, "X-CSRF-Token": client.get("/api/auth").json()["csrf"]}


@pytest.fixture
def serveur_http(parametres, monkeypatch):
    # Only this fixture permits TCP, restricted to its own pre-bound loopback socket.
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    connecteur = socket.socket.connect

    def connecter(sock, adresse):
        if sock.family == socket.AF_INET and adresse == ("127.0.0.1", port):
            erreur = socket.socket.connect_ex(sock, adresse)
            if erreur:
                raise OSError(erreur, os.strerror(erreur))
            return None
        return connecteur(sock, adresse)

    monkeypatch.setattr(socket.socket, "connect", connecter)
    enregistrer_secret(parametres.racine, "PLATFORM_UI_KEY", parametres.cle)
    code = """import os, uvicorn
from plateforme.app import creer_app
from plateforme.config import Parametres
from plateforme.moteur import Moteur
from plateforme.services import Services
class MoteurSansExecution(Moteur):
    async def demarrer(self):
        self.depot.reprendre_apres_arret()
async def sante_simulee(self):
    return {"services": [], "modeles": [], "index": {}, "ok": True}
Services.sante = sante_simulee
uvicorn.run(creer_app(Parametres.charger(), moteur_classe=MoteurSansExecution),
    fd=int(os.environ["TEST_SOCKET_FD"]), access_log=False, log_level="error", proxy_headers=False)
"""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(parametres.racine),
        "PLATFORM_ROOT": str(parametres.racine),
        "PLATFORM_STATE_DIR": str(parametres.etat),
        "PLATFORM_PORT": str(port),
        "TEST_SOCKET_FD": str(listener.fileno()),
    }
    processus = subprocess.Popen(
        [sys.executable, "-c", code],
        env=env,
        pass_fds=(listener.fileno(),),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    client = httpx.Client(
        base_url=f"http://127.0.0.1:{port}",
        trust_env=False,
        timeout=5,
        headers={"Authorization": "Bearer " + parametres.cle},
    )
    try:
        fin = time.monotonic() + 10
        while True:
            assert processus.poll() is None, "Le serveur de test n'a pas démarré."
            try:
                if client.get("/api/ping").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() >= fin:
                pytest.fail("Le serveur HTTP isolé n'est pas devenu prêt à temps.")
            time.sleep(0.02)
        yield client
    finally:
        client.close()
        processus.terminate()
        try:
            processus.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            processus.kill()
            processus.communicate(timeout=5)
        listener.close()
