"""Functional Linux host checks, independent of any running API or operator data."""

from __future__ import annotations

import argparse
import asyncio
import ctypes.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def chemin_outils() -> str:
    local = str(Path.home() / ".local/bin")
    if any(character in local for character in "\n\r\x00:"):
        raise ValueError("Unsupported host-tool path")
    return local + ":/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


async def verifier(*, export_requis: bool = False) -> dict:
    from .documents import extraire

    checks = {
        "linux": sys.platform == "linux",
        "venv": sys.prefix != sys.base_prefix,
        "bubblewrap": bool(shutil.which("bwrap")),
        "libseccomp": bool(ctypes.util.find_library("seccomp")),
        "extraction_isolee": False,
    }
    if all(checks[name] for name in ("linux", "venv", "bubblewrap", "libseccomp")):
        try:
            async with asyncio.timeout(8):
                checks["extraction_isolee"] = await extraire("prerequisite.txt", "eA==") == {
                    "kind": "text",
                    "text": "x",
                    "truncated": False,
                }
        except Exception:  # noqa: BLE001 -- no parser/kernel/proxy details in diagnostics.
            checks["extraction_isolee"] = False
    age = shutil.which("age")
    age_ready = False
    if age:
        try:
            result = await asyncio.to_thread(
                subprocess.run, [age, "--version"], capture_output=True, check=True, timeout=5
            )
            age_ready = result.stdout.decode().strip() == "v1.3.1"
        except OSError, subprocess.SubprocessError, UnicodeError:
            age_ready = False
    if export_requis:
        checks["age_export"] = age_ready
    return {
        "ok": all(checks.values()),
        "controles": checks,
        "age_export_disponible": age_ready,
        "export_requis": export_requis,
        "donnees_operateur_lues": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--avec-export", action="store_true")
    args = parser.parse_args()
    os.environ["PATH"] = chemin_outils()
    result = asyncio.run(verifier(export_requis=args.avec_export))
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
