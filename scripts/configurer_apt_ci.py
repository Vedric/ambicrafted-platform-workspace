"""Prefer official Ubuntu HTTPS mirrors on disposable GitHub runners only."""

from __future__ import annotations

import json
import os
import platform
import re
import secrets
import stat
import subprocess
import tempfile
from enum import StrEnum
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


class CodeRefus(StrEnum):
    RUNNER_CONTEXT = "runner_context"
    OS_VERSION = "os_version"
    FILE_TARGET = "file_target"
    FILE_READ = "file_read"
    FILE_TYPE = "file_type"
    FILE_OWNER = "file_owner"
    FILE_MODE = "file_mode"
    FILE_PATH = "file_path"
    TEMP_COLLISION = "temp_collision"
    SOURCES_URIS = "sources_uris"
    MIRRORS_LAYOUT = "mirrors_layout"
    TIMEOUTS_LAYOUT = "timeouts_layout"
    SOURCES_CHANGED = "sources_changed"
    MIRRORS_NOT_APPLIED = "mirrors_not_applied"
    TIMEOUTS_NOT_APPLIED = "timeouts_not_applied"
    EFFECTIVE_TIMEOUTS = "effective_timeouts"


class RefusPreparation(RuntimeError):
    def __init__(
        self,
        code: CodeRefus,
        *,
        cible: str | None = None,
        metadonnees: dict[str, int | bool] | None = None,
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.cible = cible
        self.metadonnees = metadonnees or {}

    def diagnostic(self) -> dict[str, object]:
        resultat: dict[str, object] = {
            "ok": False,
            "error_type": "RefusPreparation",
            "code": self.code.value,
        }
        if self.cible in ("sources", "mirrors", "timeouts"):
            resultat["target"] = self.cible
        # Deliberately exclude paths, file contents and arbitrary error text.
        for cle in ("uid", "mode", "regular", "symlink", "canonical", "errno"):
            valeur = self.metadonnees.get(cle)
            if type(valeur) in (int, bool):
                resultat[cle] = valeur
        return resultat


def exiger(condition: bool, code: CodeRefus) -> None:
    if not condition:
        raise RefusPreparation(code)


def lire_configuration(chemin: Path) -> bytes:
    cible = {SOURCES: "sources", MIROIRS: "mirrors", DELAIS: "timeouts"}.get(chemin)
    exiger(cible is not None, CodeRefus.FILE_TARGET)
    try:
        info = chemin.lstat()
        metadonnees = {
            "uid": info.st_uid,
            "mode": stat.S_IMODE(info.st_mode),
            "regular": stat.S_ISREG(info.st_mode),
            "symlink": stat.S_ISLNK(info.st_mode),
            "canonical": chemin.resolve() == chemin,
        }
        for valide, code in (
            (metadonnees["regular"], CodeRefus.FILE_TYPE),
            (info.st_uid == PROPRIETAIRE_ATTENDU, CodeRefus.FILE_OWNER),
            (not info.st_mode & 0o022, CodeRefus.FILE_MODE),
            (metadonnees["canonical"], CodeRefus.FILE_PATH),
        ):
            if not valide:
                raise RefusPreparation(code, cible=cible, metadonnees=metadonnees)
        return chemin.read_bytes()
    except OSError as erreur:
        raise RefusPreparation(
            CodeRefus.FILE_READ,
            cible=cible,
            metadonnees={"errno": erreur.errno} if erreur.errno is not None else {},
        ) from None


def installer_atomiquement(fichier: Path, destination: Path) -> None:
    voisin = destination.with_name(
        f".{destination.name}.platform-ci-{secrets.token_hex(16)}"
    )
    exiger(
        not voisin.exists() and not voisin.is_symlink(),
        CodeRefus.TEMP_COLLISION,
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


def lire_delais_effectifs(sortie: str) -> dict[str, int]:
    valeurs: dict[str, int] = {}
    for ligne in sortie.splitlines():
        correspondance = re.fullmatch(
            r"(HTTP_TIMEOUT|HTTPS_TIMEOUT)='([0-9]{1,2})'", ligne
        )
        if correspondance is None:
            raise RefusPreparation(CodeRefus.EFFECTIVE_TIMEOUTS)
        nom, nombre = correspondance.groups()
        valeur = int(nombre)
        exiger(nom not in valeurs and 1 <= valeur <= 30, CodeRefus.EFFECTIVE_TIMEOUTS)
        valeurs[nom] = valeur
    exiger(
        set(valeurs) == {"HTTP_TIMEOUT", "HTTPS_TIMEOUT"}, CodeRefus.EFFECTIVE_TIMEOUTS
    )
    return {"http": valeurs["HTTP_TIMEOUT"], "https": valeurs["HTTPS_TIMEOUT"]}


def preparer() -> dict[str, int]:
    # Check the execution context before reading or changing any APT setting.
    exiger(
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
        and os.environ.get("RUNNER_OS") == "Linux",
        CodeRefus.RUNNER_CONTEXT,
    )
    systeme = platform.freedesktop_os_release()
    exiger(
        systeme.get("ID") == "ubuntu" and systeme.get("VERSION_ID") == "24.04",
        CodeRefus.OS_VERSION,
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
        CodeRefus.SOURCES_URIS,
    )
    miroirs = lire_configuration(MIROIRS)
    exiger(miroirs in (ORIGINAL, PREFERENCE), CodeRefus.MIRRORS_LAYOUT)
    # Validate both destinations before the first privileged write. Refuse an
    # existing unrelated file rather than replacing administrator configuration.
    delais = (
        lire_configuration(DELAIS) if DELAIS.exists() or DELAIS.is_symlink() else None
    )
    exiger(delais in (None, DELAIS_ATTENDUS), CodeRefus.TIMEOUTS_LAYOUT)
    changements = [(MIROIRS, miroirs, PREFERENCE), (DELAIS, delais, DELAIS_ATTENDUS)]
    with tempfile.TemporaryDirectory(prefix="platform-ci-apt-") as dossier:
        for index, (destination, avant, apres) in enumerate(changements):
            if avant == apres:
                continue
            fichier = Path(dossier) / str(index)
            fichier.write_bytes(apres)
            installer_atomiquement(fichier, destination)
    exiger(lire_configuration(SOURCES) == sources, CodeRefus.SOURCES_CHANGED)
    exiger(lire_configuration(MIROIRS) == PREFERENCE, CodeRefus.MIRRORS_NOT_APPLIED)
    exiger(
        lire_configuration(DELAIS) == DELAIS_ATTENDUS, CodeRefus.TIMEOUTS_NOT_APPLIED
    )
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
    return lire_delais_effectifs(effectifs.stdout)


def main() -> int:
    try:
        effectifs = preparer()
    except RefusPreparation as erreur:
        print(json.dumps(erreur.diagnostic()))
        return 1
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as erreur:
        # Do not echo command output, environment or arbitrary file contents.
        print(json.dumps({"ok": False, "error_type": type(erreur).__name__}))
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "primary": "https://archive.ubuntu.com/ubuntu/",
                "apt_connection_and_inactivity_limit_seconds": 30,
                "apt_effective_timeout_seconds": effectifs,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
