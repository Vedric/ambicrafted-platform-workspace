"""Regenerate public, fixed welcome speech with the pinned local voice engine.

No microphone, customer data, API credentials or network are used. Run from any
directory with Python's standard library; the voice application itself uses uv.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import wave

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "apps/console/public/audio"
TEXTS = {
    "en": "Hi Védric, good to have you back. What are we working on today? We can look into an incident, talk through an architecture, or pick up where we left off. Take your time, I'm here.",
    "fr": "Bonjour Védric, contente de vous retrouver. On regarde quoi ensemble aujourd’hui ? Un incident à creuser, une architecture à préparer, ou simplement une idée dont vous voulez parler ? Prenez votre temps, je vous écoute.",
}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    uv = shutil.which("uv") or str(Path.home() / ".local/bin/uv")
    records = []
    for language, text in TEXTS.items():
        path = OUTPUT / f"aura-welcome-{language}.wav"
        # The engine correctly rejects public output directories. Generate in
        # a private temporary directory, then explicitly publish this fixed text.
        with tempfile.TemporaryDirectory(prefix="ambicrafted-welcome-") as temporary:
            private_output = Path(temporary) / "welcome.wav"
            subprocess.run(
                [
                    uv,
                    "run",
                    "--locked",
                    "--project",
                    str(ROOT / "apps/voice"),
                    "python",
                    "-m",
                    "voix_locale.cli",
                    "parler",
                    "--langue",
                    language,
                    "--sortie",
                    str(private_output),
                ],
                input=text,
                text=True,
                check=True,
                capture_output=True,
                env={
                    key: value
                    for key, value in os.environ.items()
                    if key
                    in {"HOME", "PATH", "LANG", "VOICE_STATE_DIR", "UV_CACHE_DIR"}
                },
            )
            path.write_bytes(private_output.read_bytes())
        with wave.open(str(path)) as wav:
            duration = wav.getnframes() / wav.getframerate()
        records.append(
            {
                "language": language,
                "file": path.name,
                "voice_alias": f"voix-feminine-{language}",
                "transcript": text,
                "duration_s": round(duration, 3),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    (OUTPUT / "welcome-provenance.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            [
                {
                    "language": r["language"],
                    "duration_s": r["duration_s"],
                    "bytes": r["bytes"],
                }
                for r in records
            ]
        )
    )


if __name__ == "__main__":
    main()
