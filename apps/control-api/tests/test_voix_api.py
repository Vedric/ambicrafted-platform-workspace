"""Voice API privacy, concurrency and bounded subprocess protocol."""

import asyncio
import base64
import io
import json
import os
import sys
import wave
from pathlib import Path

import pytest
from fastapi import HTTPException

from plateforme.voix import Voix


def wav_synthetique():
    flux = io.BytesIO()
    with wave.open(flux, "wb") as sortie:
        sortie.setnchannels(1)
        sortie.setsampwidth(2)
        sortie.setframerate(16000)
        sortie.writeframes(b"\x00\x00" * 160)
    return flux.getvalue()


@pytest.fixture
def runtime_voix(application, monkeypatch):
    appels = []
    audio = wav_synthetique()

    async def executer(arguments, texte=""):
        appels.append((arguments, texte))
        if arguments == ["statut"]:
            return {"pret": True, "local": True, "voix": "voix-feminine-fr", "langue": "fr-FR"}
        chemin = Path(arguments[-1])
        assert chemin.parent.stat().st_mode & 0o777 == 0o700
        if arguments[0] == "parler":
            fd = os.open(chemin, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as fichier:
                fichier.write(audio)
            return {"local": True, "format": "wav"}
        assert arguments[0] == "transcrire"
        assert chemin.stat().st_mode & 0o777 == 0o600
        assert chemin.read_bytes() == audio
        return {"texte": "Phrase synthétique", "langue": "fr", "local": True, "duree_s": 0.01}

    monkeypatch.setattr(application.state.voix, "executer", executer)
    return appels, audio


@pytest.mark.parametrize(
    "route,charge",
    [
        ("/api/voix/parler", {"texte": "Bonjour"}),
        ("/api/voix/transcrire", {"audio": "U1lOVEhFVElRVUU="}),
        ("/api/assistant/dialogue", {"messages": [{"role": "user", "content": "Bonjour"}]}),
    ],
)
def test_voix_et_dialogue_exigent_authentification(client, route, charge):
    assert client.post(route, json=charge).status_code == 401
    assert client.get("/api/voix/statut").status_code == 401


def test_synthese_transcription_locales_et_nettoyage(client, application, bearer, runtime_voix):
    appels, audio = runtime_voix
    assert client.get("/api/voix/statut", headers=bearer).json()["pret"] is True
    assert client.get("/api/voix/statut", headers=bearer).json()["local"] is True
    assert sum(a[0] == ["statut"] for a in appels) == 1
    reponse = client.post("/api/voix/parler", headers=bearer, json={"texte": "Bonjour synthétique"})
    assert reponse.status_code == 200 and reponse.content == audio
    assert reponse.headers["content-type"] == "audio/wav"
    assert reponse.headers["cache-control"] == "no-store"
    transcription = client.post(
        "/api/voix/transcrire", headers=bearer, json={"audio": base64.b64encode(audio).decode()}
    )
    assert (
        transcription.status_code == 200 and transcription.json()["texte"] == "Phrase synthétique"
    )
    assert list(application.state.voix.temp.iterdir()) == []
    assert "Phrase synthétique" not in json.dumps(application.state.depot.journal())
    assert "Bonjour synthétique" not in json.dumps(application.state.depot.journal())


def test_voix_cookie_exige_csrf_et_micro_autorise_uniquement_soi(client, session):
    reponse = client.post("/api/voix/parler", json={"texte": "Bonjour"})
    assert reponse.status_code == 403
    assert "microphone=(self)" in reponse.headers["permissions-policy"]
    assert "media-src 'self' blob:" in reponse.headers["content-security-policy"]


@pytest.mark.parametrize(
    "charge", [{"texte": " "}, {"texte": "x" * 2001}, {"texte": "Bonjour", "voix": "arbitraire"}]
)
def test_synthese_charge_strictement_bornee(client, bearer, charge):
    assert client.post("/api/voix/parler", headers=bearer, json=charge).status_code == 422


@pytest.mark.parametrize("audio", ["!!!", "é", "data:audio/wav;base64,UklGRg=="])
def test_audio_base64_invalide_refuse(client, bearer, audio):
    assert (
        client.post("/api/voix/transcrire", headers=bearer, json={"audio": audio}).status_code
        == 422
    )


def test_limite_corps_audio_specifique_sans_elargir_autres_routes(
    client, application, bearer, monkeypatch
):
    appels = []

    async def transcrire(audio):
        appels.append(len(audio))
        return {"texte": "Synthétique", "local": True}

    monkeypatch.setattr(application.state.voix, "transcrire", transcrire)
    encoded = base64.b64encode(b"x" * 100_000).decode()
    assert (
        client.post("/api/voix/transcrire", headers=bearer, json={"audio": encoded}).status_code
        == 200
    )
    assert appels == [len(encoded)]
    assert (
        client.post("/api/voix/parler", headers=bearer, json={"texte": encoded}).status_code == 413
    )
    assert (
        client.post(
            "/api/analyses", headers=bearer, json={"titre": "Test", "alerte": encoded}
        ).status_code
        == 413
    )
    assert (
        client.post(
            "/api/voix/transcrire",
            headers={**bearer, "Content-Length": "12000000"},
            json={"audio": "UklGRg=="},
        ).status_code
        == 413
    )


@pytest.mark.asyncio
async def test_taille_audio_decodee_refusee_avant_ecriture(parametres):
    voix = Voix(parametres)
    for audio in [b"", b"x" * 8_388_609]:
        with pytest.raises(HTTPException) as erreur:
            await voix.transcrire(base64.b64encode(audio).decode())
        assert erreur.value.status_code == 413
    assert list(voix.temp.iterdir()) == []


@pytest.mark.asyncio
async def test_file_voix_occupee_refuse_sans_accumuler(parametres):
    voix = Voix(parametres)
    async with voix.verrou:
        for appel in [voix.parler("Bonjour"), voix.transcrire("UklGRg==")]:
            with pytest.raises(HTTPException) as erreur:
                await appel
            assert erreur.value.status_code == 409
    assert list(voix.temp.iterdir()) == []


@pytest.mark.asyncio
async def test_voix_echec_nettoie_toujours_fichier_prive(parametres, monkeypatch):
    voix = Voix(parametres)

    async def erreur(*args, **kwargs):
        raise HTTPException(503, "Échec synthétique")

    monkeypatch.setattr(voix, "executer", erreur)
    for appel in [
        voix.parler("Bonjour"),
        voix.transcrire(base64.b64encode(wav_synthetique()).decode()),
    ]:
        with pytest.raises(HTTPException):
            await appel
        assert list(voix.temp.iterdir()) == []
        assert not voix.verrou.locked()


@pytest.mark.asyncio
@pytest.mark.parametrize("resultat", [{"texte": None}, {"texte": 7}, {"texte": "x" * 20_001}])
async def test_transcription_sortie_malformee_refusee(parametres, monkeypatch, resultat):
    voix = Voix(parametres)

    async def executer(*args, **kwargs):
        return resultat

    monkeypatch.setattr(voix, "executer", executer)
    with pytest.raises(HTTPException) as erreur:
        await voix.transcrire(base64.b64encode(wav_synthetique()).decode())
    assert erreur.value.status_code == 502
    assert list(voix.temp.iterdir()) == []


@pytest.mark.asyncio
async def test_sortie_audio_symbolique_refusee(parametres, monkeypatch, tmp_path):
    voix = Voix(parametres)
    prive = tmp_path / "prive.wav"
    prive.write_bytes(wav_synthetique())

    async def executer(arguments, texte=""):
        Path(arguments[-1]).symlink_to(prive)
        return {"local": True}

    monkeypatch.setattr(voix, "executer", executer)
    with pytest.raises((HTTPException, OSError)):
        await voix.parler("Bonjour")
    assert prive.exists() and list(voix.temp.iterdir()) == []


def executable_voix(parametres, code):
    executable = parametres.racine / "apps/voice/.venv/bin/voix-locale"
    executable.parent.mkdir(parents=True)
    executable.write_text(f"#!{sys.executable}\n" + code)
    executable.chmod(0o700)


@pytest.mark.asyncio
async def test_protocole_voix_accepte_json_fragmente(parametres):
    executable_voix(
        parametres,
        "import sys, time\nsys.stdout.write('{\"pret\":'); sys.stdout.flush()\ntime.sleep(0.05)\nsys.stdout.write('true,\"local\":true}'); sys.stdout.flush()\n",
    )
    assert await Voix(parametres).executer(["statut"]) == {"pret": True, "local": True}


@pytest.mark.asyncio
async def test_protocole_voix_sortie_excessive_bornee_sans_blocage(parametres):
    executable_voix(parametres, "import os\nos.write(1, b'x' * 1_000_000)\n")
    async with asyncio.timeout(5):
        with pytest.raises(HTTPException) as erreur:
            await Voix(parametres).executer(["statut"])
    assert erreur.value.status_code == 502


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code,statut",
    [
        ("print('invalid json')", 503),
        ("print('[]')", 503),
        ("print('secret synthétique'); raise SystemExit(2)", 422),
    ],
)
async def test_protocole_voix_erreurs_masquees(parametres, code, statut):
    executable_voix(parametres, code)
    with pytest.raises(HTTPException) as erreur:
        await Voix(parametres).executer(["statut"])
    assert erreur.value.status_code == statut
    assert "secret synthétique" not in erreur.value.detail


@pytest.mark.asyncio
async def test_sortie_fifo_refusee_sans_blocage(parametres, monkeypatch):
    voix = Voix(parametres)

    async def executer(arguments, texte=""):
        os.mkfifo(arguments[-1])
        return {"local": True}

    monkeypatch.setattr(voix, "executer", executer)
    with pytest.raises(HTTPException) as erreur:
        await voix.parler("Bonjour")
    assert erreur.value.status_code == 502
    assert list(voix.temp.iterdir()) == []


@pytest.mark.asyncio
async def test_annulation_transcription_libere_verrou_et_fichier(parametres, monkeypatch):
    voix = Voix(parametres)
    commence = asyncio.Event()

    async def executer(arguments, texte=""):
        assert Path(arguments[-1]).exists()
        commence.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(voix, "executer", executer)
    travail = asyncio.create_task(voix.transcrire(base64.b64encode(wav_synthetique()).decode()))
    async with asyncio.timeout(3):
        await commence.wait()
        travail.cancel()
        with pytest.raises(asyncio.CancelledError):
            await travail
    assert list(voix.temp.iterdir()) == []
    assert not voix.verrou.locked()


def test_audio_abandonne_nettoye_sans_suivre_liens(parametres, tmp_path):
    from plateforme.voix import Voix

    voix = Voix(parametres)
    orphelin = voix.temp / "capture-interruption"
    orphelin.mkdir(mode=0o700)
    (orphelin / "audio").write_bytes(b"synthetic")
    preserve = voix.temp / "notes-operateur"
    preserve.mkdir(mode=0o700)
    externe = tmp_path / "externe"
    externe.mkdir()
    (externe / "preuve").write_text("conserver")
    (voix.temp / "capture-lien").symlink_to(externe, target_is_directory=True)
    voix.nettoyer_apres_arret()
    assert not orphelin.exists()
    assert preserve.is_dir()
    assert (externe / "preuve").read_text() == "conserver"
