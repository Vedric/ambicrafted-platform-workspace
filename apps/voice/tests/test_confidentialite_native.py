"""Use fresh native processes: Python socket mocks cannot observe native 1DS."""

import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "module", ["voix_locale", "voix_locale.cli", "voix_locale.resident", "voix_locale.synthese"]
)
def test_import_natif_sans_identifiant_persistant(tmp_path, module):
    # The old implementation creates :memory:.ses even in a network namespace.
    # Deliberately contradict the privacy setting inherited from this test runner.
    code = """
import importlib, sys
importlib.import_module(sys.argv[1])
from piper.phonemize_espeak import EspeakPhonemizer
import onnxruntime
onnxruntime.SessionOptions()
"""
    resultat = subprocess.run(
        [sys.executable, "-c", code, module],
        cwd=tmp_path,
        env={**os.environ, "ORT_DISABLE_TELEMETRY": "0"},
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert resultat.returncode == 0, resultat.stderr
    assert not list(tmp_path.iterdir()), "Native import persisted unexpected telemetry state"
