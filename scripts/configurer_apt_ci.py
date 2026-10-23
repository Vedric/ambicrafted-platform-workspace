"""Prefer official Ubuntu HTTPS mirrors on disposable GitHub runners only."""

from __future__ import annotations

import json
import os
import platform
import secrets
import stat
import subprocess
import tempfile
from pathlib import Path

MIROIRS = Path("/etc/apt/apt-mirrors.txt")
SOURCES = Path("/etc/apt/sources.list.d/ubuntu.sources")
DELAIS = Path("/etc/apt/apt.conf.d/99platform-ci-network")
PROPRIETAIRE_ATTENDU = 0
ORIGINAL = (
    b"http://azure.archive.ubuntu.com/ubuntu/\tpriority:1\n"
    b"https://archive.ubuntu.com/ubuntu/\tpriority:2\n"
    b"https://security.ubuntu.com/ubuntu/\tpriority:3\n"
)
PREFERENCE = (
    b"https://archive.ubuntu.com/ubuntu/\tpriority:1\n"
    b"https://security.ubuntu.com/ubuntu/\tpriority:2\n"
    b"http://azure.archive.ubuntu.com/ubuntu/\tpriority:3\n"
)
DELAIS_ATTENDUS = b'Acquire::http::Timeout "30";\nAcquire::https::Timeout "30";\n'


def exiger(condition: bool, raison: str) -> None:
    if not condition:
        raise RuntimeError(raison)


def lire_configuration(chemin: Path) -> bytes:
    info = chemin.lstat()
    exiger(
        stat.S_ISREG(info.st_mode)
        and info.st_uid == PROPRIETAIRE_ATTENDU
        and not info.st_mode & 0o022
        and chemin.resolve() == chemin,
        "Configuration APT inattendue : propriétaire, permissions ou lien.",
    )
    return chemin.read_bytes()


def installer_atomiquement(fichier: Path, destination: Path) -> None:
    voisin = destination.with_name(
        f".{destination.name}.platform-ci-{secrets.token_hex(16)}"
    )
    exiger(
        not voisin.exists() and not voisin.is_symlink(),
        "Fichier temporaire déjà présent.",
    )
    try:
        subprocess.run(
            [
                "sudo",
                "--non-interactive",
                "install",
                "--owner=root",
                "--group=root",
                "--mode=0644",
                str(fichier),
                str(voisin),
            ],
            check=True,
            timeout=15,
        )
        subprocess.run(
            [
                "sudo",
                "--non-interactive",
                "mv",
                "--no-target-directory",
                "--",
                str(voisin),
                str(destination),
            ],
            check=True,
            timeout=15,
        )
    finally:
        if voisin.exists() or voisin.is_symlink():
            subprocess.run(
                ["sudo", "--non-interactive", "rm", "--", str(voisin)],
                check=True,
                timeout=15,
            )


def preparer() -> None:
    # Check the execution context before reading or changing any APT setting.
    exiger(
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
        and os.environ.get("RUNNER_OS") == "Linux",
        "Préparation réservée aux runners Linux hébergés par GitHub.",
    )
    systeme = platform.freedesktop_os_release()
    exiger(
        systeme.get("ID") == "ubuntu" and systeme.get("VERSION_ID") == "24.04",
        "Seule la configuration Ubuntu 24.04 a été qualifiée.",
    )
    sources = lire_configuration(SOURCES)
    uris: list[list[str]] = []
    continuation_uri = False
    for ligne in sources.decode().splitlines():
        if not ligne.strip():
            continuation_uri = False
        elif ligne.startswith("#"):
            continue
        elif ligne[:1].isspace():
            if continuation_uri:
                uris[-1].extend(ligne.split())
        else:
            cle, _, valeur = ligne.partition(":")
            continuation_uri = cle.strip().casefold() == "uris"
            if continuation_uri:
                uris.append(valeur.split())
    exiger(
        bool(uris)
        and all(uri == ["mirror+file:/etc/apt/apt-mirrors.txt"] for uri in uris),
        "Câblage des sources Ubuntu différent du runner qualifié.",
    )
    miroirs = lire_configuration(MIROIRS)
    exiger(miroirs in (ORIGINAL, PREFERENCE), "Liste des miroirs Ubuntu inattendue.")
    # Validate both destinations before the first privileged write. Refuse an
    # existing unrelated file rather than replacing administrator configuration.
    delais = (
        lire_configuration(DELAIS) if DELAIS.exists() or DELAIS.is_symlink() else None
    )
    exiger(
        delais in (None, DELAIS_ATTENDUS), "Configuration des délais déjà différente."
    )
    changements = [(MIROIRS, miroirs, PREFERENCE), (DELAIS, delais, DELAIS_ATTENDUS)]
    with tempfile.TemporaryDirectory(prefix="platform-ci-apt-") as dossier:
        for index, (destination, avant, apres) in enumerate(changements):
            if avant == apres:
                continue
            fichier = Path(dossier) / str(index)
            fichier.write_bytes(apres)
            installer_atomiquement(fichier, destination)
    exiger(lire_configuration(SOURCES) == sources, "Les sources Ubuntu ont changé.")
    exiger(lire_configuration(MIROIRS) == PREFERENCE, "Priorités APT non appliquées.")
    exiger(lire_configuration(DELAIS) == DELAIS_ATTENDUS, "Délais APT non appliqués.")
    effectifs = subprocess.run(
        [
            "apt-config",
            "shell",
            "HTTP_TIMEOUT",
            "Acquire::http::Timeout",
            "HTTPS_TIMEOUT",
            "Acquire::https::Timeout",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    exiger(
        effectifs.stdout.splitlines() == ["HTTP_TIMEOUT='30'", "HTTPS_TIMEOUT='30'"],
        "Les délais APT effectifs diffèrent de la configuration qualifiée.",
    )


def main() -> int:
    try:
        preparer()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as erreur:
        # Do not echo command output, environment or arbitrary file contents.
        print(json.dumps({"ok": False, "error_type": type(erreur).__name__}))
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "primary": "https://archive.ubuntu.com/ubuntu/",
                "apt_connection_and_inactivity_seconds": 30,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
