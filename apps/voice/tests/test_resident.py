import json
import subprocess
import sys

import pytest

from voix_locale import resident
from voix_locale.fichiers import ErreurVoix


@pytest.mark.parametrize(
    "charge",
    [
        None,
        [],
        {},
        {"operation": "installer"},
        {"operation": "parler", "langue": "fr", "fichier": "/unused", "texte": []},
        {"operation": "transcrire", "langue": "de", "fichier": "/unused"},
        {"operation": "transcrire", "langue": "fr", "fichier": "/unused", "extra": True},
    ],
)
def test_operations_strictes(charge):
    with pytest.raises(ErreurVoix):
        resident.traiter(charge)


@pytest.mark.parametrize(
    "entree", [b'{"secret":"CLIENT-PRIVATE"}\n', b"x" * 40_000, b"[]\n", b"{}"]
)
def test_erreur_protocole_natif_bornee_et_privee(entree):
    p = subprocess.run(
        [sys.executable, "-m", "voix_locale.resident"],
        input=entree,
        capture_output=True,
        timeout=5,
        check=False,
    )
    assert p.stdout == b'{"erreur":true}\n'
    assert not p.stderr and b"CLIENT-PRIVATE" not in p.stdout


def test_plusieurs_operations_un_meme_processus_sans_echo_prive():
    # Exercise the real pipe/framing loop with only native inference replaced.
    code = """
from voix_locale import resident
resident.traiter = lambda r: {"langue": r["langue"]}
resident.main()
"""
    frames = [
        {"id": "a" * 32, "langue": "fr", "texte": "PRIVATE"},
        {"id": "b" * 32, "langue": "en"},
    ]
    p = subprocess.run(
        [sys.executable, "-c", code],
        input="".join(json.dumps(f) + "\n" for f in frames),
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )
    assert p.returncode == 0 and not p.stderr
    assert [json.loads(s) for s in p.stdout.splitlines()] == [
        {"id": "a" * 32, "resultat": {"langue": "fr"}},
        {"id": "b" * 32, "resultat": {"langue": "en"}},
    ]


def test_arret_automatique_apres_inactivite():
    p = subprocess.Popen(
        [
            sys.executable,
            "-c",
            """
from voix_locale import resident
resident.INACTIVITE_SECONDES = 1
resident.main()
""",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert p.wait(timeout=5) == 0
        out, err = p.communicate()
        assert not out and not err
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()


def test_cache_recognition_reutilise_et_limite_les_modeles(tmp_path, monkeypatch):
    import faster_whisper

    from voix_locale.moteur import modele_reconnaissance

    calls = []

    def model(path, **options):
        calls.append((path, options))
        return object()

    monkeypatch.setattr(faster_whisper, "WhisperModel", model)
    modele_reconnaissance.cache_clear()
    try:
        fr = modele_reconnaissance(tmp_path / "fr", "fr")
        assert modele_reconnaissance(tmp_path / "fr", "fr") is fr
        modele_reconnaissance(tmp_path / "en-short", "en")
        modele_reconnaissance(tmp_path / "en-long", "en")
        assert modele_reconnaissance.cache_info().currsize == 2
        assert modele_reconnaissance(tmp_path / "fr", "fr") is not fr
        assert len(calls) == 4
        assert calls[0][1]["compute_type"] == "float32"
        assert calls[1][1]["compute_type"] == "int8"
    finally:
        modele_reconnaissance.cache_clear()
