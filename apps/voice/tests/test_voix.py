"""Private media boundaries and reproducible model installation without network access."""

import hashlib
import io
import json
import os
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

from voix_locale import fichiers, moteur
from voix_locale.fichiers import ErreurVoix


def audio(path: Path, secondes: float = 1, frequence: int = 16000, canaux: int = 1) -> Path:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(canaux)
        wav.setsampwidth(2)
        wav.setframerate(frequence)
        wav.writeframes(bytes(int(secondes * frequence) * canaux * 2))
    path.chmod(0o600)
    return path


def cli(*args: str, stdin: bytes = b"", etat: Path | None = None):
    environnement = dict(os.environ)
    if etat:
        environnement["VOICE_STATE_DIR"] = str(etat)
    return subprocess.run(
        [sys.executable, "-m", "voix_locale.cli", *args],
        input=stdin,
        capture_output=True,
        timeout=10,
        env=environnement,
        check=False,
    )


@pytest.mark.parametrize("texte", ["", "  ", "x" * 2001, "secret\x00", "secret\x1b[31m"])
def test_texte_refuse(texte):
    with pytest.raises(ErreurVoix):
        moteur.valider_texte(texte)


def test_texte_unicode_et_borne():
    assert moteur.valider_texte("  Bonjour\nÉloïse !  ") == "Bonjour\nÉloïse !"
    assert len(moteur.valider_texte("é" * 2000)) == 2000


@pytest.mark.parametrize("langue", ["de", "en-US", "../fr", ""])
def test_langue_invalide_refusee_avant_fichier_ou_modele(tmp_path, langue):
    with pytest.raises(ErreurVoix, match="Langue"):
        moteur.parler("Hello", tmp_path / "sortie.wav", langue)
    with pytest.raises(ErreurVoix, match="Langue"):
        moteur.transcrire(tmp_path / "inexistant.wav", langue)
    assert not (tmp_path / "sortie.wav").exists()


def test_reconnaissance_longue_et_fr_partagent_les_poids_courte_en_isolee():
    aliases = fichiers.manifeste()["aliases"]
    assert aliases["transcription-en"]["repertoire"] == aliases["transcription-fr"]["repertoire"]
    assert aliases["transcription-en"]["fichiers"] == aliases["transcription-fr"]["fichiers"]
    courte = aliases["transcription-en-courte"]
    assert courte["repertoire"] != aliases["transcription-en"]["repertoire"]
    assert courte["fichiers"] != aliases["transcription-en"]["fichiers"]
    assert courte["langue"] == "en" and courte["licence"] == "MIT"


@pytest.mark.parametrize(
    ("langue", "echantillons", "alias_modele"),
    [
        ("en", 467200, "transcription-en-courte"),
        ("en", 467201, "transcription-en"),
        ("fr", 467200, "transcription-fr"),
    ],
)
def test_routage_sur_echantillons_decodes_et_alias_public_stable(
    tmp_path, monkeypatch, langue, echantillons, alias_modele
):
    from types import SimpleNamespace

    import faster_whisper

    path = tmp_path / "frontiere.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(bytes(echantillons * 2))
    path.chmod(0o600)
    verifications = []

    def verifier(alias):
        verifications.append(alias)
        return tmp_path / alias

    class Reconnaissance:
        def __init__(self, dossier, **_options):
            assert dossier == str(tmp_path / alias_modele)

        def transcribe(self, signal, **options):
            assert len(signal) == echantillons + 12800
            assert options["language"] == langue
            assert options.get("without_timestamps", False) is False
            assert options["beam_size"] == 10 and options["temperature"] == 0
            return iter([SimpleNamespace(text="Synthetic boundary.")]), None

    monkeypatch.setattr(moteur, "verifier_modele", verifier)
    monkeypatch.setattr(faster_whisper, "WhisperModel", Reconnaissance)
    resultat = moteur.transcrire(path, langue)
    assert verifications == [alias_modele]
    assert resultat["alias"] == "transcription-" + langue
    # Both English boundary inputs round to the same public duration.
    assert resultat["duree_s"] == 29.2


def test_backend_fixe_avant_import_natif_meme_si_environnement_contradictoire():
    code = """import importlib.abc, os, sys
from pathlib import Path
from voix_locale.moteur import modele_reconnaissance
class InspecterImport(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'faster_whisper':
            assert os.environ['CT2_USE_MKL'] == '0'
            assert os.environ['HF_HUB_OFFLINE'] == '1'
            raise RuntimeError('bootstrap-verified')
sys.meta_path.insert(0, InspecterImport())
try:
    modele_reconnaissance(Path('/unused-synthetic-model'), 'fr')
except RuntimeError as error:
    assert str(error) == 'bootstrap-verified'
    print('verified')
else:
    raise AssertionError('The native import must pass through the guard.')
"""
    resultat = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "CT2_USE_MKL": "1"},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert resultat.returncode == 0
    assert resultat.stdout == "verified\n" and resultat.stderr == ""


@pytest.mark.parametrize("secondes", [0.2, 90])
@pytest.mark.parametrize("langue", ["en", "fr"])
def test_contexte_acoustique_preserve_signal_bornes_et_duree(
    tmp_path, monkeypatch, secondes, langue
):
    from types import SimpleNamespace

    import faster_whisper

    path = tmp_path / "source.wav"
    source = np.full(int(secondes * moteur.FREQUENCE), 1234, dtype=np.int16)
    source[0], source[-1] = -12345, 23456
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(moteur.FREQUENCE)
        wav.writeframes(source.tobytes())
    path.chmod(0o600)

    class Reconnaissance:
        def __init__(self, *_args, **options):
            assert options["device"] == "cpu"
            assert options["compute_type"] == ("float32" if langue == "fr" else "int8")
            assert options["cpu_threads"] == 4
            assert options["local_files_only"] is True

        def transcribe(self, signal, **options):
            contexte = moteur.FREQUENCE * moteur.CONTEXTE_AUDIO_MS // 1000
            assert signal.dtype == np.float32
            assert len(signal) == len(source) + 2 * contexte
            assert not np.any(signal[:contexte])
            assert not np.any(signal[-contexte:])
            np.testing.assert_array_equal(signal[contexte:-contexte], source / 32768.0)
            assert options["vad_filter"] is True
            assert options["beam_size"] == 10
            assert options["vad_parameters"]["speech_pad_ms"] == moteur.CONTEXTE_AUDIO_MS
            return iter([SimpleNamespace(text="A synthetic result.")]), None

    monkeypatch.setattr(faster_whisper, "WhisperModel", Reconnaissance)
    monkeypatch.setattr(moteur, "verifier_modele", lambda _alias: tmp_path)
    resultat = moteur.transcrire(path, langue)
    assert resultat["duree_s"] == secondes
    assert resultat["texte"] == "A synthetic result."


def test_dossiers_crees_prives(tmp_path):
    cible = tmp_path / "a" / "b"
    fichiers.dossier_prive(cible, creer=True)
    assert cible.stat().st_mode & 0o777 == 0o700
    assert cible.parent.stat().st_mode & 0o777 == 0o700


def test_dossier_public_refuse(tmp_path):
    tmp_path.chmod(0o755)
    with pytest.raises(ErreurVoix):
        fichiers.dossier_prive(tmp_path)


def test_dossier_symlink_et_chemin_relatif_refuses(tmp_path):
    dossier = tmp_path / "dossier"
    dossier.mkdir(mode=0o700)
    lien = tmp_path / "lien"
    lien.symlink_to(dossier, target_is_directory=True)
    for path in (lien, Path("relatif")):
        with pytest.raises(ErreurVoix):
            fichiers.dossier_prive(path)


def test_audio_symlink_refuse(tmp_path):
    original = audio(tmp_path / "original.wav")
    lien = tmp_path / "lien.wav"
    lien.symlink_to(original)
    with pytest.raises(OSError):
        moteur.decoder_audio(lien)


def test_fifo_refuse_sans_bloquer(tmp_path):
    chemin = tmp_path / "pipe"
    os.mkfifo(chemin, 0o600)
    with pytest.raises(ErreurVoix), fichiers.ouvrir_prive(chemin, 20):
        pytest.fail("A FIFO must never be read")


def test_audio_public_refuse(tmp_path):
    chemin = audio(tmp_path / "public.wav")
    chemin.chmod(0o644)
    with pytest.raises(ErreurVoix):
        moteur.decoder_audio(chemin)


def test_audio_trop_gros_refuse_avant_decodage(tmp_path):
    chemin = tmp_path / "gros.wav"
    with chemin.open("wb") as stream:
        stream.truncate(moteur.MAX_AUDIO_OCTETS + 1)
    chemin.chmod(0o600)
    with pytest.raises(ErreurVoix):
        moteur.decoder_audio(chemin)


def test_audio_trop_long_refuse(tmp_path):
    with pytest.raises(ErreurVoix, match="90 secondes"):
        moteur.decoder_audio(audio(tmp_path / "long.wav", 90.01))


def test_audio_trop_court_refuse(tmp_path):
    with pytest.raises(ErreurVoix, match="0,2 seconde"):
        moteur.decoder_audio(audio(tmp_path / "court.wav", 0.1))


@pytest.mark.parametrize("frequence,canaux", [(16000, 1), (48000, 2), (22050, 1)])
def test_decodage_format_navigateur_vers_mono_16khz(tmp_path, frequence, canaux):
    resultat = moteur.decoder_audio(audio(tmp_path / "silence.wav", 1, frequence, canaux))
    assert resultat.shape == (16000,)
    assert resultat.dtype == np.float32
    assert not resultat.any()


def test_audio_degrade_ne_fuit_pas_dans_la_cli(tmp_path):
    path = tmp_path / "audio.wav"
    path.write_bytes(b"DONNEES_CLIENT_CONFIDENTIELLES" * 20)
    path.chmod(0o600)
    resultat = cli("transcrire", str(path))
    assert resultat.returncode == 2
    assert "erreur" in json.loads(resultat.stdout)
    assert b"CONFIDENTIELLES" not in resultat.stdout + resultat.stderr
    assert resultat.stderr == b""


@pytest.mark.parametrize("contenu", [b"\xff", b"x" * 8001, b" ", b"interdit\x00"])
def test_cli_synthese_entree_invalide(tmp_path, contenu):
    path = tmp_path / "sortie.wav"
    resultat = cli("parler", "--sortie", str(path), stdin=contenu)
    assert resultat.returncode == 2
    assert "erreur" in json.loads(resultat.stdout)
    assert not path.exists()
    assert not resultat.stderr


def test_statut_absent_est_explicite(tmp_path):
    resultat = cli("statut", etat=tmp_path)
    assert resultat.returncode == 2
    assert "erreur" in json.loads(resultat.stdout)
    assert str(tmp_path).encode() not in resultat.stdout


@pytest.fixture
def modele_minimal(tmp_path, monkeypatch):
    octets = b"model-known-content"
    definition = {
        "aliases": {
            "transcription-fr": {
                "repertoire": "transcription",
                "fichiers": [
                    {
                        "nom": "model.bin",
                        "octets": len(octets),
                        "sha256": hashlib.sha256(octets).hexdigest(),
                        "url": "https://huggingface.co/organisation/depot/resolve/revision/model.bin",
                    }
                ],
            }
        }
    }
    monkeypatch.setenv("VOICE_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(fichiers, "manifeste", lambda: definition)
    monkeypatch.setattr(fichiers, "urlopen", lambda *args, **kwargs: io.BytesIO(octets))
    return tmp_path, definition, octets


def test_installation_verifie_et_reutilise(modele_minimal, monkeypatch):
    racine, _, octets = modele_minimal
    assert fichiers.installer()["fichiers_installes"] == 1
    path = racine / "transcription/model.bin"
    assert path.read_bytes() == octets
    assert path.stat().st_mode & 0o777 == 0o600
    monkeypatch.setattr(fichiers, "urlopen", lambda *a, **k: pytest.fail("Unexpected network"))
    assert fichiers.installer()["fichiers_installes"] == 0
    assert fichiers.verifier_modele("transcription-fr") == racine / "transcription"


def test_telechargement_corrompu_ne_publie_pas(modele_minimal, monkeypatch):
    racine, _, octets = modele_minimal
    monkeypatch.setattr(fichiers, "urlopen", lambda *a, **k: io.BytesIO(b"x" * len(octets)))
    with pytest.raises(ErreurVoix, match="empreinte"):
        fichiers.installer()
    assert not (racine / "transcription/model.bin").exists()
    assert list((racine / "transcription").iterdir()) == []


@pytest.mark.parametrize("difference", [-1, 1])
def test_telechargement_taille_exacte_requise(modele_minimal, monkeypatch, difference):
    racine, _, octets = modele_minimal
    monkeypatch.setattr(
        fichiers, "urlopen", lambda *a, **k: io.BytesIO(b"x" * (len(octets) + difference))
    )
    with pytest.raises(ErreurVoix):
        fichiers.installer()
    assert not (racine / "transcription/model.bin").exists()


def test_fichier_modele_corrompu_refuse(modele_minimal):
    racine, _, octets = modele_minimal
    fichiers.installer()
    (racine / "transcription/model.bin").write_bytes(b"x" * len(octets))
    with pytest.raises(ErreurVoix, match="Intégrité"):
        fichiers.verifier_modele("transcription-fr")


def test_source_de_telechargement_autorisee(modele_minimal):
    _, definition, _ = modele_minimal
    definition["aliases"]["transcription-fr"]["fichiers"][0]["url"] = "http://example.com/a"
    with pytest.raises(ErreurVoix, match="Source"):
        fichiers.installer()


def test_configuration_runtime_force_hors_ligne(monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    moteur.hors_ligne()
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["HF_HUB_DISABLE_TELEMETRY"] == "1"
