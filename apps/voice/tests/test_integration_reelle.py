"""Opt-in real models. Run under an isolated network namespace after installation."""

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
def test_voix_francaise_et_reponse_micro_navigateur(tmp_path, format, extension, codec):
    wav = tmp_path / "salutation.wav"
    metadata = parler(
        "Bonjour, je suis votre assistante locale. La plateforme protège vos données. "
        "Voulez-vous analyser une alerte ?",
        wav,
    )
    assert metadata["format"] == "wav"
    assert metadata["frequence_hz"] == 22050
    assert 3 < metadata["duree_s"] < 15
    assert wav.stat().st_mode & 0o777 == 0o600
    path = wav
    if codec:
        path = tmp_path / ("navigateur." + extension)
        encoder(wav, path, format, codec)
    resultat = transcrire(path)
    for mot in ("bonjour", "assistante", "locale", "plateforme", "données", "alerte"):
        assert mot in resultat["texte"].lower()
    assert resultat["local"]


def test_silence_ne_devient_pas_une_instruction(tmp_path):
    path = tmp_path / "silence.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(bytes(3 * 16000 * 2))
    path.chmod(0o600)
    assert transcrire(path)["texte"] == ""


def test_synthese_necrase_jamais_un_fichier(tmp_path):
    path = tmp_path / "existant.wav"
    path.write_bytes(b"contenu original")
    path.chmod(0o600)
    with pytest.raises(FileExistsError):
        parler("Bonjour.", path)
    assert path.read_bytes() == b"contenu original"


def test_processus_cli_reel_sans_journal_client(tmp_path):
    resultat = subprocess.run(
        [sys.executable, "-m", "voix_locale.cli", "parler", "--sortie", str(tmp_path / "cli.wav")],
        input="Bonjour, bienvenue dans votre plateforme privée.",
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert resultat.returncode == 0
    assert "Bienvenue" not in resultat.stdout
    assert resultat.stderr == ""
