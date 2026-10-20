"""Encrypt a verified backup with age, or stage its recovery without replacing live data."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from inventaire_sauvegarde import (
    MAX_BYTES,
    MAX_FILES,
    lire_manifeste,
    nom_relatif,
    ouvrir_fichier,
    verifier_inventaire,
    verifier_repertoire,
)

AGE_VERSION = "v1.3.1"
MAX_ARCHIVE = MAX_BYTES + MAX_FILES * 8192 + 8 * 1024**2


class LectureVerifiee:
    """Hash exactly the bytes consumed by tar, independent of later source changes."""

    def __init__(self, source, expected: dict) -> None:
        self.source = source
        self.expected = expected
        self.digest = hashlib.sha256()
        self.size = 0

    def read(self, size: int) -> bytes:
        block = self.source.read(size)
        self.digest.update(block)
        self.size += len(block)
        if self.size > self.expected["octets"]:
            raise ValueError("Backup member changed during archive creation")
        return block

    def verifier(self) -> None:
        if (
            self.size != self.expected["octets"]
            or self.digest.hexdigest() != self.expected["sha256"]
        ):
            raise ValueError("Backup member changed during archive creation")


def age() -> str:
    executable = shutil.which("age")
    if not executable:
        raise ValueError("age is required; see docs/RECOVERY.md")
    version = (
        subprocess.run(
            [executable, "--version"],
            capture_output=True,
            check=True,
            timeout=10,
        )
        .stdout.decode()
        .strip()
    )
    if version != AGE_VERSION:
        raise ValueError("Use the qualified age version documented in docs/RECOVERY.md")
    return executable


def dossier_prive(parent: Path, relative: str) -> Path:
    current = parent
    for piece in nom_relatif(relative).split("/"):
        current = current / piece
        current.mkdir(mode=0o700, exist_ok=True)
        verifier_repertoire(current, prive=True)
    return current


def extraire(archive, destination: Path) -> None:
    """Never use extractall on an untrusted archive: only bounded, unique regular members."""
    verifier_repertoire(destination, prive=True)
    seen, total = set(), 0
    # Only USTAR regular files. Parse one bounded header before any payload allocation:
    # even PAX/GNU extended headers are refused, avoiding attacker-sized metadata reads.
    while True:
        header = archive.read(512)
        if len(header) != 512:
            raise ValueError("Truncated archive")
        if header == b"\0" * 512:
            if archive.read(512) != b"\0" * 512:
                raise ValueError("Incomplete archive trailer")
            for block in iter(lambda: archive.read(1024 * 1024), b""):
                if any(block):
                    raise ValueError("Unexpected archive trailer")
            return
        member = tarfile.TarInfo.frombuf(header, encoding="utf-8", errors="strict")
        name = nom_relatif(member.name)
        if (
            name in seen
            or len(seen) >= MAX_FILES + 1
            or member.type not in {tarfile.REGTYPE, tarfile.AREGTYPE}
        ):
            raise ValueError("Unsupported or duplicate archive member")
        seen.add(name)
        total += member.size
        if member.size < 0 or total > MAX_BYTES + 8 * 1024**2:
            raise ValueError("Archive byte limit exceeded")
        target = destination / name
        if target.parent != destination:
            dossier_prive(
                destination, target.parent.relative_to(destination).as_posix()
            )
        fd = os.open(
            target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(fd, "wb") as sortie:
            remaining = member.size
            while remaining:
                block = archive.read(min(remaining, 1024 * 1024))
                if not block:
                    raise ValueError("Truncated archive payload")
                remaining -= len(block)
                sortie.write(block)
            sortie.flush()
            os.fsync(sortie.fileno())
        padding = (-member.size) % 512
        if archive.read(padding) != b"\0" * padding:
            raise ValueError("Invalid archive padding")


def chiffrer(source: Path, destinataires: Path, sortie: Path) -> dict:
    verifier_repertoire(sortie.parent, prive=True)
    if sortie.is_relative_to(source):
        raise ValueError("Export destination must be outside the backup")
    manifeste = lire_manifeste(source)
    resultat = verifier_inventaire(source, manifeste, obligatoire=True)
    with ouvrir_fichier(destinataires, prive=False) as recipients:
        public = recipients.read(64 * 1024 + 1)
    if len(public) > 64 * 1024 or not public.strip():
        raise ValueError("Invalid recipient file")
    # Accept native public recipients only. No SSH keys, plugins or secret identities.
    lines = [
        line.strip()
        for line in public.decode().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not lines or any(
        not line.startswith("age1") or not line.isalnum() for line in lines
    ):
        raise ValueError("Native age public recipients required")
    executable = age()
    with tempfile.TemporaryDirectory(
        prefix="platform-encrypt-", dir=sortie.parent
    ) as temporary:
        private = Path(temporary)
        recipients_copy = private / "recipients.txt"
        recipients_copy.write_bytes(public)
        recipients_copy.chmod(0o600)
        with tempfile.TemporaryFile(dir=private) as archive:
            with tarfile.open(
                fileobj=archive, mode="w", format=tarfile.USTAR_FORMAT
            ) as bundle:
                # Archive the already validated manifest, never reread it through tar.
                frozen_manifest = json.dumps(manifeste, ensure_ascii=False).encode()
                info = tarfile.TarInfo("manifest.json")
                info.size, info.mode = len(frozen_manifest), 0o600
                bundle.addfile(info, io.BytesIO(frozen_manifest))
                expected = {entry["fichier"]: entry for entry in manifeste["integrite"]}
                for name in sorted(expected):
                    path = source / name
                    with ouvrir_fichier(path) as entree:
                        info = tarfile.TarInfo(name)
                        info.size = expected[name]["octets"]
                        info.mode = 0o600
                        verified = LectureVerifiee(entree, expected[name])
                        bundle.addfile(info, verified)
                        verified.verifier()
            verifier_inventaire(source, manifeste, obligatoire=True)
            if lire_manifeste(source) != manifeste:
                raise ValueError("Backup manifest changed during export")
            archive.seek(0)
            fd = os.open(
                sortie, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            complete = False
            try:
                with os.fdopen(fd, "wb") as output:
                    subprocess.run(
                        [executable, "--encrypt", "-R", str(recipients_copy)],
                        stdin=archive,
                        stdout=output,
                        stderr=subprocess.PIPE,
                        timeout=300,
                        check=True,
                    )
                    output.flush()
                    os.fsync(output.fileno())
                complete = True
            finally:
                if not complete:
                    sortie.unlink(missing_ok=True)
    with ouvrir_fichier(sortie) as encrypted:
        digest = hashlib.file_digest(encrypted, "sha256").hexdigest()
    return {
        **resultat,
        "archive_chiffree": str(sortie),
        "sha256": digest,
        "copie_hors_poste_verifiee": False,
        "age": AGE_VERSION,
    }


def dechiffrer(source: Path, identite: Path, sortie: Path) -> dict:
    verifier_repertoire(sortie.parent, prive=True)
    if sortie.exists() or sortie.is_symlink():
        raise FileExistsError("Recovery destination must not exist")
    # The private identity is read only by age, never embedded in the archive or diagnostics.
    with ouvrir_fichier(identite):
        pass
    executable = age()
    with ouvrir_fichier(source) as encrypted:
        if os.fstat(encrypted.fileno()).st_size > MAX_ARCHIVE:
            raise ValueError("Encrypted archive too large")
        with tempfile.TemporaryDirectory(
            prefix="platform-decrypt-", dir=sortie.parent
        ) as temporary:
            staging = Path(temporary)
            with tempfile.TemporaryFile(dir=staging) as archive:
                subprocess.run(
                    [executable, "--decrypt", "-i", str(identite)],
                    stdin=encrypted,
                    stdout=archive,
                    stderr=subprocess.PIPE,
                    timeout=300,
                    check=True,
                )
                # Authenticate the entire payload before parsing or publishing any backup file.
                if archive.tell() > MAX_ARCHIVE:
                    raise ValueError("Decrypted archive too large")
                archive.seek(0)
                unpacked = staging / "backup"
                unpacked.mkdir(mode=0o700)
                extraire(archive, unpacked)
            manifeste = lire_manifeste(unpacked)
            resultat = verifier_inventaire(unpacked, manifeste, obligatoire=True)
            # mkdir reserves the destination without overwriting any existing operator directory.
            sortie.mkdir(mode=0o700)
            try:
                for path in unpacked.iterdir():
                    path.rename(sortie / path.name)
            except BaseException:
                # It is ours and was empty before this operation. Never touch another destination.
                shutil.rmtree(sortie)
                raise
    return {
        **resultat,
        "dossier_restauration": str(sortie),
        "services_actifs_modifies": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    encryption = actions.add_parser(
        "encrypt", help="Export a complete, inventoried backup"
    )
    encryption.add_argument("source", type=Path)
    encryption.add_argument("--recipients", type=Path, required=True)
    encryption.add_argument("--output", type=Path, required=True)
    recovery = actions.add_parser(
        "restore", help="Decrypt into a new private staging directory"
    )
    recovery.add_argument("source", type=Path)
    recovery.add_argument("--identity", type=Path, required=True)
    recovery.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        source, output = (
            args.source.expanduser().absolute(),
            args.output.expanduser().absolute(),
        )
        if args.action == "encrypt":
            result = chiffrer(source, args.recipients.expanduser().absolute(), output)
        else:
            result = dechiffrer(source, args.identity.expanduser().absolute(), output)
        print(json.dumps(result))
        return 0
    except Exception as erreur:  # noqa: BLE001 -- no file names/content or age diagnostics on failure.
        print(
            json.dumps(
                {
                    "erreur": type(erreur).__name__,
                    "message": "Backup export/recovery failed; no live service was changed.",
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
