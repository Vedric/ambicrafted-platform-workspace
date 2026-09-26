"""Bounded reads of regular Markdown files, without following symlinks."""

from __future__ import annotations

import os
import stat
from pathlib import Path

MAX_OCTETS = 200_000
MAX_FICHIERS = 1_000


def verifier_nom(nom: str) -> None:
    if (
        not isinstance(nom, str)
        or not nom.endswith(".md")
        or nom.startswith(".")
        or "/" in nom
        or "\\" in nom
        or "\x00" in nom
    ):
        raise ValueError("Nom de fichier Markdown invalide.")


def lire(repertoire: Path, nom: str, *, maximum: int = MAX_OCTETS) -> str:
    verifier_nom(nom)
    racine = os.open(repertoire, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        # O_NONBLOCK prevents a FIFO from hanging before fstat can refuse it.
        fd = os.open(nom, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=racine)
        with os.fdopen(fd, "rb") as fichier:
            info = os.fstat(fichier.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("Seuls les fichiers réguliers sont autorisés.")
            if info.st_size > maximum:
                raise ValueError("Runbook trop volumineux ; le diviser avant lecture.")
            contenu = fichier.read(maximum + 1)
            if len(contenu) > maximum:
                raise ValueError("Runbook trop volumineux ; le diviser avant lecture.")
            return contenu.decode("utf-8", errors="replace")
    finally:
        os.close(racine)


def noms(repertoire: Path) -> list[str]:
    resultat: list[str] = []
    examines = 0
    with os.scandir(repertoire) as entrees:
        for entree in entrees:
            examines += 1
            if examines > MAX_FICHIERS:
                raise ValueError("Corpus trop volumineux : au plus 1 000 entrées.")
            if entree.name.endswith(".md") and not entree.name.startswith("."):
                resultat.append(entree.name)
    return sorted(resultat)
