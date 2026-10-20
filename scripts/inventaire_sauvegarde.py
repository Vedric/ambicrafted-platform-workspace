"""Private, bounded backup inventory; no file contents appear in diagnostics."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path, PurePosixPath

MAX_FILES = 20_000
MAX_BYTES = 8 * 1024**3
MAX_SOURCE_FILE = 256 * 1024**2


def nom_relatif(nom: str) -> str:
    if (
        not isinstance(nom, str)
        or not nom
        or "\\" in nom
        or "\x00" in nom
        or PurePosixPath(nom).is_absolute()
        or any(part in {"", ".", ".."} for part in nom.split("/"))
        or len(nom) > 1024
        or len(nom.split("/")) > 32
    ):
        raise ValueError("Invalid backup member path")
    return nom


def verifier_repertoire(dossier: Path, *, prive: bool = False) -> None:
    if not dossier.is_absolute() or dossier.resolve() != dossier:
        raise ValueError("Absolute directory without symbolic links required")
    info = dossier.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & (0o077 if prive else 0o022)
    ):
        raise ValueError("Owned directory with safe permissions required")


def ouvrir_fichier(chemin: Path, *, prive: bool = True):
    verifier_repertoire(chemin.parent, prive=prive)
    fd = os.open(chemin, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & (0o077 if prive else 0o022)
            or info.st_size > MAX_BYTES
        ):
            raise ValueError("Owned regular file with safe permissions required")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def creer_parents(racine: Path, relative: Path) -> None:
    courant = racine
    for part in relative.parts:
        courant /= part
        courant.mkdir(mode=0o700, exist_ok=True)
        verifier_repertoire(courant, prive=True)


def erreur_parcours(error: OSError) -> None:
    raise error


def fichiers(dossier: Path) -> list[Path]:
    verifier_repertoire(dossier, prive=True)
    result = []
    entries = 0
    for parent, directories, names in os.walk(
        dossier, followlinks=False, onerror=erreur_parcours
    ):
        root = Path(parent)
        verifier_repertoire(root, prive=True)
        entries += len(directories) + len(names)
        if entries > MAX_FILES * 2:
            raise ValueError("Backup entry limit exceeded")
        for name in directories:
            nom_relatif((root / name).relative_to(dossier).as_posix())
            verifier_repertoire(root / name, prive=True)
        for name in names:
            nom_relatif((root / name).relative_to(dossier).as_posix())
            result.append(root / name)
            if len(result) > MAX_FILES:
                raise ValueError("Backup file limit exceeded")
    return sorted(result)


def inventaire(dossier: Path) -> list[dict]:
    result, total = [], 0
    for fichier in fichiers(dossier):
        if fichier == dossier / "manifest.json":
            continue
        digest, size = hashlib.sha256(), 0
        with ouvrir_fichier(fichier) as entree:
            for block in iter(lambda: entree.read(1024 * 1024), b""):
                size += len(block)
                total += len(block)
                if total > MAX_BYTES:
                    raise ValueError("Backup byte limit exceeded")
                digest.update(block)
        result.append(
            {
                "fichier": fichier.relative_to(dossier).as_posix(),
                "octets": size,
                "sha256": digest.hexdigest(),
            }
        )
    return result


def verifier_inventaire(
    dossier: Path, manifeste: dict, *, obligatoire: bool = False
) -> dict:
    attendu = manifeste.get("integrite")
    if attendu is None and not obligatoire:
        return {"integrite_verifiee": False, "format_ancien": True}
    if not isinstance(attendu, list) or not attendu or len(attendu) > MAX_FILES:
        raise ValueError("Missing or invalid backup integrity inventory")
    actual = inventaire(dossier)
    # Exact list comparison also rejects duplicates, changed sizes, unlisted files and paths.
    if actual != attendu:
        raise ValueError("Backup inventory or checksum mismatch")
    return {
        "integrite_verifiee": True,
        "fichiers_verifies": len(actual),
        "octets_verifies": sum(row["octets"] for row in actual),
    }


def lire_manifeste(dossier: Path) -> dict:
    with ouvrir_fichier(dossier / "manifest.json") as entree:
        encoded = entree.read(8 * 1024**2 + 1)
    if len(encoded) > 8 * 1024**2:
        raise ValueError("Backup manifest too large")
    value = json.loads(encoded)
    if (
        not isinstance(value, dict)
        or value.get("type") != "platform-backup-v1"
        or value.get("complet") is not True
    ):
        raise ValueError("Incomplete or unsupported backup")
    return value


def copier_sources(corpus: Path, autres: list[Path], destination: Path) -> dict:
    """Copy the active top-level Markdown corpus and explicit full mission directories."""
    verifier_repertoire(destination, prive=True)
    if len(autres) > 16:
        raise ValueError("At most sixteen additional source directories are supported")
    sources = [("runbooks", corpus, True)] + [
        (f"missions/{number:02d}", source, False)
        for number, source in enumerate(autres)
    ]
    details, total, count, entries = [], 0, 0, 0
    for label, source, markdown_only in sources:
        verifier_repertoire(source)
        if destination.is_relative_to(source) or source.is_relative_to(destination):
            raise ValueError("Backup and source trees must not overlap")
        cible = destination / "sources" / label
        creer_parents(destination, cible.relative_to(destination))
        copied = 0
        for parent, directories, names in os.walk(
            source, followlinks=False, onerror=erreur_parcours
        ):
            current = Path(parent)
            verifier_repertoire(current)
            if markdown_only:
                if len(directories) + len(names) > 1000:
                    raise ValueError("Runbook corpus entry limit exceeded")
                directories.clear()
                names = [
                    n for n in names if n.endswith(".md") and not n.startswith(".")
                ]
            for directory in directories:
                nom_relatif((current / directory).relative_to(source).as_posix())
                verifier_repertoire(current / directory)
            entries += len(directories) + len(names)
            if entries > MAX_FILES * 2:
                raise ValueError("Source entry limit exceeded")
            for name in sorted(names):
                relative = (current / name).relative_to(source)
                nom_relatif(relative.as_posix())
                target = cible / relative
                creer_parents(destination, target.parent.relative_to(destination))
                with ouvrir_fichier(current / name, prive=False) as entree:
                    info = os.fstat(entree.fileno())
                    limit = 200_000 if markdown_only else MAX_SOURCE_FILE
                    if info.st_size > limit:
                        raise ValueError("Source file size limit exceeded")
                    fd = os.open(
                        target,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600,
                    )
                    with os.fdopen(fd, "wb") as sortie:
                        size = 0
                        for block in iter(lambda: entree.read(1024 * 1024), b""):
                            size += len(block)
                            total += len(block)
                            if size > limit or total > MAX_BYTES:
                                raise ValueError("Source data size limit exceeded")
                            sortie.write(block)
                    after = os.fstat(entree.fileno())
                    if (info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (
                        after.st_size,
                        after.st_mtime_ns,
                        after.st_ctime_ns,
                    ):
                        raise ValueError(
                            "Source changed during backup; retry after quiescing writers"
                        )
                copied += 1
                count += 1
                if count > MAX_FILES:
                    raise ValueError("Source file count limit exceeded")
        details.append(
            {
                "source": str(source),
                "destination": "sources/" + label,
                "fichiers": copied,
                "selection": "markdown-actif" if markdown_only else "complete",
            }
        )
    return {
        "repertoires": details,
        "fichiers": count,
        "octets": total,
        "atomicite_multi_bases": False,
    }
