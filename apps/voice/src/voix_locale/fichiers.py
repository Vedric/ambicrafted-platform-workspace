"""Private descriptor-based file access and bounded model installation."""

import fcntl
import hashlib
import json
import os
import secrets
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlparse
from urllib.request import urlopen


class ErreurVoix(Exception):
    """An operator-safe error; never includes input or low-level error details."""


def dossier_prive(path: Path, creer: bool = False) -> Path:
    if not path.is_absolute() or path.resolve() != path:
        raise ErreurVoix("Un chemin absolu sans lien symbolique est requis.")
    if creer:
        absents = []
        parent = path
        while not parent.exists():
            absents.append(parent)
            parent = parent.parent
        for parent in reversed(absents):
            parent.mkdir(mode=0o700, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ErreurVoix("Le dossier doit appartenir à cet utilisateur et être privé (700).")
    return path


def etat() -> Path:
    return dossier_prive(
        Path(
            os.environ.get("VOICE_STATE_DIR", str(Path.home() / ".local/state/ambicrafted/voice"))
        ),
        creer=True,
    )


@contextmanager
def ouvrir_prive(path: Path, maximum: int) -> Iterator[BinaryIO]:
    dossier_prive(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
            or info.st_size > maximum
        ):
            raise ErreurVoix("Fichier privé régulier requis, dans la limite de taille autorisée.")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            yield stream
    finally:
        os.close(fd)


def manifeste() -> dict:
    return json.loads(files("voix_locale").joinpath("modeles.json").read_text())


def empreinte(path: Path, taille: int) -> str:
    with ouvrir_prive(path, taille) as stream:
        digest = hashlib.sha256()
        total = 0
        while bloc := stream.read(1024 * 1024):
            total += len(bloc)
            if total > taille:
                raise ErreurVoix("Le modèle dépasse la taille épinglée.")
            digest.update(bloc)
        if total != taille:
            raise ErreurVoix("Le modèle est incomplet.")
        return digest.hexdigest()


def verifier_modele(alias: str) -> Path:
    definition = manifeste()["aliases"][alias]
    dossier = dossier_prive(etat() / definition["repertoire"])
    for fichier in definition["fichiers"]:
        if empreinte(dossier / fichier["nom"], fichier["octets"]) != fichier["sha256"]:
            raise ErreurVoix("Intégrité du modèle invalide ; relancez l’installation vocale.")
    return dossier


def installer() -> dict:
    racine = etat()
    fd = os.open(racine / ".installation.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        copies = 0
        for definition in manifeste()["aliases"].values():
            dossier = dossier_prive(racine / definition["repertoire"], creer=True)
            for fichier in definition["fichiers"]:
                destination = dossier / fichier["nom"]
                try:
                    if empreinte(destination, fichier["octets"]) == fichier["sha256"]:
                        continue
                except (OSError, ErreurVoix):
                    pass
                url = fichier["url"]
                if urlparse(url).scheme != "https" or urlparse(url).hostname != "huggingface.co":
                    raise ErreurVoix("Source du modèle non autorisée.")
                temporaire = dossier / (".telechargement-" + secrets.token_hex(12))
                sortie = os.open(temporaire, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                try:
                    with os.fdopen(sortie, "wb") as stream, urlopen(url, timeout=60) as response:
                        total = 0
                        while bloc := response.read(1024 * 1024):
                            total += len(bloc)
                            if total > fichier["octets"]:
                                raise ErreurVoix("Le téléchargement dépasse la taille épinglée.")
                            stream.write(bloc)
                        stream.flush()
                        os.fsync(stream.fileno())
                    if empreinte(temporaire, fichier["octets"]) != fichier["sha256"]:
                        raise ErreurVoix(
                            "Le téléchargement ne correspond pas à l’empreinte épinglée."
                        )
                    os.replace(temporaire, destination)
                    copies += 1
                finally:
                    temporaire.unlink(missing_ok=True)
        return {"pret": True, "fichiers_installes": copies, "local": True}
    except BlockingIOError as error:
        raise ErreurVoix("Une installation vocale est déjà en cours.") from error
    finally:
        os.close(fd)
