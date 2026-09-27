"""Opt-in real models. Run under an isolated network namespace after installation."""

import hashlib
import json
import os
import subprocess
import sys
import wave
from pathlib import Path

import av
import pytest

from voix_locale.moteur import parler, transcrire

pytestmark = pytest.mark.skipif(
    os.environ.get("VOICE_TEST_REAL") != "1",
    reason="VOICE_TEST_REAL=1 and pinned local models required",
)


@pytest.mark.parametrize(
    "langue,phrase",
    [
        (
            "fr",
            "Bonjour Védric, on regarde votre pipeline GitHub Enterprise sur Kubernetes ensemble ? On peut commencer par les logs, puis vérifier le rollback.",
        ),
        (
            "en",
            "Hi Védric, let's check your GitHub Enterprise pipeline on Kubernetes together. We can start with the logs, then check the rollback.",
        ),
    ],
)
def test_termes_techniques_dans_une_phrase_continue(tmp_path, langue, phrase):
    wav = tmp_path / "technical.wav"
    metadata = parler(phrase, wav, langue)
    assert metadata["frequence_hz"] == 24000
    assert 4 < metadata["duree_s"] < 20
    transcript = transcrire(wav, langue)["texte"].casefold()
    for term in ("github", "enterprise", "kubernetes", "rollback"):
        assert term in transcript
    if langue == "fr":
        assert "bonjour védric" in transcript


def encoder(source: Path, cible: Path, format: str, codec: str) -> None:
    with av.open(str(source)) as entree, av.open(str(cible), "w", format=format) as sortie:
        flux = sortie.add_stream(codec, rate=48000)
        flux.layout = "mono"
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=48000)
        for frame in entree.decode(audio=0):
            for mono in resampler.resample(frame):
                for paquet in flux.encode(mono):
                    sortie.mux(paquet)
        for mono in resampler.resample(None):
            for paquet in flux.encode(mono):
                sortie.mux(paquet)
        for paquet in flux.encode():
            sortie.mux(paquet)
    cible.chmod(0o600)


@pytest.mark.parametrize(
    "format,extension,codec",
    [("wav", "wav", ""), ("webm", "webm", "libopus"), ("ogg", "ogg", "libopus")],
)
@pytest.mark.parametrize(
    "langue,phrase,mots",
    [
        (
            "en",
            (
                "Hello, I am your local assistant. The platform protects your data. "
                "Would you like to analyze an alert?"
            ),
            ("hello", "local", "assistant", "platform", "data", "alert"),
        ),
        (
            "fr",
            (
                "Bonjour, je suis votre assistante locale. La plateforme protège vos données. "
                "Voulez-vous analyser une alerte ?"
            ),
            ("bonjour", "assistante", "locale", "plateforme", "données", "alerte"),
        ),
    ],
)
def test_voix_bilingue_et_reponse_micro_navigateur(
    tmp_path, format, extension, codec, langue, phrase, mots
):
    wav = tmp_path / "salutation.wav"
    metadata = parler(phrase, wav, langue)
    assert metadata["format"] == "wav"
    assert metadata["frequence_hz"] == 24000
    assert 3 < metadata["duree_s"] < 15
    assert wav.stat().st_mode & 0o777 == 0o600
    path = wav
    if codec:
        path = tmp_path / ("navigateur." + extension)
        encoder(wav, path, format, codec)
    resultat = transcrire(path, langue)
    for mot in mots:
        assert mot in resultat["texte"].lower()
    assert resultat["local"]
    assert metadata["langue"] == resultat["langue"] == langue
    assert metadata["alias"] == "voix-feminine-" + langue
    assert resultat["alias"] == "transcription-" + langue


@pytest.mark.parametrize(
    "format,extension,codec",
    [("wav", "wav", ""), ("webm", "webm", "libopus"), ("ogg", "ogg", "libopus")],
)
def test_debut_de_parole_preserve_sur_signal_de_regression(tmp_path, format, extension, codec):
    source = Path(__file__).parent / "fixtures" / "english-onset.wav"
    donnees = source.read_bytes()
    assert hashlib.sha256(donnees).hexdigest() == (
        "4617ec10d8aa913213673ee15f6fbca882b0c754a968d9610bec29252e2f8729"
    )
    wav = tmp_path / "onset.wav"
    wav.write_bytes(donnees)
    wav.chmod(0o600)
    path = wav
    if codec:
        path = tmp_path / ("navigateur." + extension)
        encoder(wav, path, format, codec)
    resultat = transcrire(path, "en")
    mots = resultat["texte"].lower()
    for mot in ("hello", "local", "assistant", "platform", "data", "alert"):
        assert mot in mots
    assert "although" not in mots
    assert 5.9 < resultat["duree_s"] < 6.1


def test_contexte_preserve_confidentialite_et_negation(tmp_path):
    donnees = (Path(__file__).parent / "fixtures" / "english-confidentiality.wav").read_bytes()
    assert hashlib.sha256(donnees).hexdigest() == (
        "ef59eaaa990183185e48cb95cfab730898a1c57943e1e6821f3acbe7f5002c85"
    )
    path = tmp_path / "confidentiality.wav"
    path.write_bytes(donnees)
    path.chmod(0o600)
    texte = transcrire(path, "en")["texte"].lower()
    assert "local workstation" in texte
    assert "do not send customer data to an external service" in texte


@pytest.mark.parametrize(
    "fixture,mots",
    [
        ("english-onset", ("hello", "local assistant", "platform", "data", "alert")),
        (
            "english-confidentiality",
            ("local workstation", "do not send customer data to an external service"),
        ),
    ],
)
def test_cli_neuf_ne_depend_pas_du_backend_mkl_herite(tmp_path, fixture, mots):
    path = tmp_path / "source.wav"
    path.write_bytes((Path(__file__).parent / "fixtures" / (fixture + ".wav")).read_bytes())
    path.chmod(0o600)
    resultat = subprocess.run(
        [sys.executable, "-m", "voix_locale.cli", "transcrire", "--langue", "en", str(path)],
        env={**os.environ, "CT2_USE_MKL": "1"},
        capture_output=True,
        text=True,
        timeout=40,
        check=False,
    )
    assert resultat.returncode == 0
    assert resultat.stderr == ""
    reponse = json.loads(resultat.stdout)
    assert reponse["local"] is True and reponse["langue"] == "en"
    assert all(mot in reponse["texte"].lower() for mot in mots)


@pytest.mark.parametrize("langue", ["en", "fr"])
def test_silence_ne_devient_pas_une_instruction(tmp_path, langue):
    path = tmp_path / "silence.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(bytes(3 * 16000 * 2))
    path.chmod(0o600)
    assert transcrire(path, langue)["texte"] == ""


def test_synthese_necrase_jamais_un_fichier(tmp_path):
    path = tmp_path / "existant.wav"
    path.write_bytes(b"contenu original")
    path.chmod(0o600)
    with pytest.raises(FileExistsError):
        parler("Hello.", path)
    assert path.read_bytes() == b"contenu original"


def test_processus_cli_reel_sans_journal_client(tmp_path):
    resultat = subprocess.run(
        [sys.executable, "-m", "voix_locale.cli", "parler", "--sortie", str(tmp_path / "cli.wav")],
        input="Hello, welcome to your private platform.",
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert resultat.returncode == 0
    assert "welcome" not in resultat.stdout
    assert resultat.stderr == ""
