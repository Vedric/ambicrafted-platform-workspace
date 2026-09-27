"""Readiness evidence, confidentiality, failure isolation and actual MCP handshake."""

import asyncio
import io
import json
import os
import sys
from unittest.mock import AsyncMock

import httpx
import pytest

from plateforme.config import enregistrer_secret
from plateforme.preparation import boucle_locale, controle, ecoutes_locales, inventorier_mcp, prive


@pytest.fixture
def preparation(application):
    return application.state.preparation


@pytest.mark.parametrize(
    "url", ["http://localhost:4000/v1", "http://127.0.0.1:6333", "http://[::1]:4318"]
)
def test_destinations_loopback(url):
    assert boucle_locale(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://api.example.invalid/v1",
        "http://localhost.attacker.invalid",
        "file:///tmp/x",
        "http://user:secret@localhost:4000",
        "http://localhost:4000?secret=x",
        "http://[invalid",
    ],
)
def test_destinations_hors_politique_refusees(url):
    assert not boucle_locale(url)


def test_permissions_sans_lecture_ni_symlink(tmp_path):
    source = tmp_path / "secret"
    source.write_text("Synthetic private content")
    source.chmod(0o600)
    assert prive(source)
    source.chmod(0o644)
    assert not prive(source)
    lien = tmp_path / "lien"
    lien.symlink_to(source)
    assert not prive(lien)
    assert not prive(tmp_path / "absent")


@pytest.mark.asyncio
async def test_configuration_reelle_permissions_et_localite(preparation, parametres):
    enregistrer_secret(parametres.racine, "PLATFORM_UI_KEY", parametres.cle)
    resultat = await preparation.configuration()
    assert all(c["status"] == "pass" for c in resultat)
    assert parametres.cle not in json.dumps(resultat)
    enregistrer_secret(parametres.racine, "LITELLM_BASE_URL", "https://remote.example.invalid/v1")
    assert (await preparation.configuration())[1]["status"] == "fail"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "alias,statut",
    [
        (["local", "local-embed"], "pass"),
        (["local", "local-embed", "remote-private-marker"], "fail"),
        (["local"], "fail"),
    ],
)
async def test_inventaire_credential_mesure_sans_exposer_alias(
    preparation, parametres, monkeypatch, alias, statut
):
    enregistrer_secret(parametres.racine, "CONFIDENTIAL_KEY", parametres.cle)
    reel = httpx.AsyncClient
    appels = []

    def repondre(requete):
        appels.append(requete)
        assert requete.method == "GET" and str(requete.url) == "http://127.0.0.1:4000/v1/models"
        assert requete.headers["authorization"] == "Bearer " + parametres.cle
        assert requete.content == b""
        return httpx.Response(200, json={"data": [{"id": a} for a in alias]})

    def client(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        return reel(transport=httpx.MockTransport(repondre), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    resultat = await preparation.routage()
    assert resultat[0]["status"] == statut and len(appels) == 1
    assert parametres.cle not in json.dumps(resultat)
    assert "remote-private-marker" not in json.dumps(resultat)


@pytest.mark.asyncio
async def test_index_vide_et_degradation_services(preparation, monkeypatch):
    monkeypatch.setattr(
        preparation.services,
        "sante",
        AsyncMock(
            return_value={
                "services": [{"id": "litellm", "ok": True}, {"id": "ollama", "ok": False}],
                "index": {"points": 0, "statut": "green"},
            }
        ),
    )
    controles = {c["id"]: c for c in await preparation.demons()}
    assert controles["service_litellm"]["status"] == "pass"
    assert controles["service_ollama"]["status"] == "fail"
    assert controles["service_prometheus"]["status"] == "warn"
    assert controles["knowledge_index"]["status"] == "warn"


@pytest.mark.asyncio
async def test_verification_cache_coalescence_echecs_et_pas_de_contenu(
    preparation, monkeypatch, parametres
):
    appels = AsyncMock(
        return_value=[controle("runtime_agent", "runtime", "pass", "Runtime", "Installed")]
    )
    monkeypatch.setattr(preparation, "runtime", appels)
    monkeypatch.setattr(
        preparation, "configuration", AsyncMock(side_effect=ValueError(parametres.cle))
    )
    monkeypatch.setattr(preparation, "routage", AsyncMock(return_value=[]))
    monkeypatch.setattr(preparation, "ecoute", AsyncMock(return_value=[]))
    monkeypatch.setattr(preparation, "mcp", AsyncMock(return_value=[]))
    monkeypatch.setattr(preparation, "vocal", AsyncMock(return_value=[]))
    un, deux = await asyncio.gather(preparation.verifier(), preparation.verifier())
    assert un == deux and appels.await_count == 1
    assert un["ready"] is False and un["capabilities"]["analysis"] is False
    assert un["summary"]["unknown"] == 1
    serialise = json.dumps(un)
    assert parametres.cle not in serialise
    assert "PostgreSQL indisponible" not in serialise
    assert "Vérifier le service avant" not in serialise
    un["checks"].clear()
    assert (await preparation.verifier())["checks"]
    preparation.date = 0
    await preparation.verifier()
    assert appels.await_count == 2


@pytest.mark.asyncio
async def test_tout_vert_sans_certification_production(preparation, monkeypatch):
    requis = [
        "runtime_agent",
        "configuration_private",
        "configuration_local",
        "configuration_listener",
        "service_litellm",
        "service_ollama",
        "service_qdrant",
        "routing_aliases",
        "knowledge_sources",
        "knowledge_index",
        "mcp_runbooks",
        "mcp_control",
        "voice_en",
        "voice_fr",
    ]
    for nom in (
        "runtime",
        "configuration",
        "ecoute",
        "demons",
        "routage",
        "connaissance",
        "vocal",
        "mcp",
    ):
        monkeypatch.setattr(preparation, nom, AsyncMock(return_value=[]))
    monkeypatch.setattr(
        preparation,
        "runtime",
        AsyncMock(
            return_value=[controle(n, "test", "pass", "Measured", "Checked") for n in requis]
        ),
    )
    resultat = await preparation.verifier()
    assert resultat["ready"] and all(resultat["capabilities"].values())
    assert "not a security or production certification" in resultat["limits"][0]


@pytest.mark.asyncio
async def test_sonde_bornee_et_annulee(preparation, monkeypatch):
    monkeypatch.setattr("plateforme.preparation.DELAI_SONDE", 0.01)
    annule = asyncio.Event()

    async def lente():
        try:
            await asyncio.sleep(10)
        finally:
            annule.set()

    resultat = await preparation.borne("mcp_control", lente)
    assert annule.is_set() and resultat[0]["status"] == "unknown"


@pytest.mark.asyncio
async def test_handshake_mcp_reel_sans_credential(monkeypatch):
    monkeypatch.setenv("CONFIDENTIAL_KEY", "SYNTHETIC_NOT_IN_CHILD_ENV")
    async with asyncio.timeout(10):
        outils = await inventorier_mcp(
            sys.executable, ["-m", "plateforme.mcp"], {"PATH": os.environ.get("PATH", "")}
        )
    assert {"plateforme_preparation", "plateforme_journal", "plateforme_recherche"} <= outils
    assert not any("approuv" in o or "execut" in o for o in outils)


def test_endpoints_authentifies_et_bornes(client, bearer, application, monkeypatch):
    attendu = {"ready": False, "scope": "local-private", "checks": []}
    monkeypatch.setattr(application.state.preparation, "verifier", AsyncMock(return_value=attendu))
    for route in ("/api/preparation", "/api/journal"):
        assert client.get(route).status_code == 401
    assert client.get("/api/preparation", headers=bearer).json() == attendu
    assert client.get("/api/journal?limite=0", headers=bearer).status_code == 422
    assert client.get("/api/journal?limite=101", headers=bearer).status_code == 422
    assert client.get("/api/journal?limite=1", headers=bearer).json() == {"elements": []}


@pytest.mark.parametrize(
    "adresse,attendu",
    [
        ("0100007F", True),
        ("00000000", False),
        ("0100000A", False),
        ("00000000000000000000000001000000", True),
        ("00000000000000000000000000000000", False),
    ],
)
def test_ecoutes_linux_ipv4_ipv6_sans_exposer_adresse(monkeypatch, adresse, attendu):
    from pathlib import Path

    def ouvrir(chemin, *_args, **_kwargs):
        assert chemin.parent == Path("/proc/net")
        version = "tcp6" if len(adresse) == 32 else "tcp"
        contenu = f"0: {adresse}:2253 00000000:0000 0A\n" if chemin.name == version else ""
        return io.StringIO("header\n" + contenu)

    monkeypatch.setattr(Path, "open", ouvrir)
    monkeypatch.setattr("plateforme.preparation.sys.byteorder", "little")
    assert ecoutes_locales(8787) == [attendu]
    assert ecoutes_locales(9999) == []
