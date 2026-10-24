# /// script
# requires-python = ">=3.14"
# dependencies = ["python-dotenv==1.2.3"]
# ///
"""Provision local service credentials without displaying or rotating existing secrets."""

from __future__ import annotations

import fcntl
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
from pathlib import Path

from dotenv import dotenv_values, set_key

RACINE = Path(__file__).resolve().parents[1]
NOMS = ("QDRANT_API_KEY", "QDRANT_READ_ONLY_API_KEY", "PROMETHEUS_PASSWORD")


def environnement(chemin: Path) -> dict[str, str]:
    if not chemin.exists() and not chemin.is_symlink():
        return {}
    info = chemin.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Un environnement privé régulier appartenant à l'utilisateur est requis.")
    return {k: v for k, v in dotenv_values(chemin).items() if v is not None}


def preparer(racine: Path) -> dict:
    """Stable credentials, fail on disagreement, private parent with individual read-only mounts."""
    programme = shutil.which("htpasswd")
    if not programme:
        raise ValueError("Installer apache2-utils (htpasswd) avant cette opération.")
    dossier = racine / "gateway/.service-auth"
    if dossier.is_symlink():
        raise ValueError("Lien symbolique refusé.")
    dossier.mkdir(mode=0o700, exist_ok=True)
    info = dossier.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Le dossier des secrets doit appartenir à l'utilisateur, en mode 0700.")
    fd = os.open(dossier / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    verrou_racine = os.open(
        racine / ".env.control.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    try:
        for verrou in (fd, verrou_racine):
            info = os.fstat(verrou)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError("Verrou de configuration non privé.")
        fcntl.flock(fd, fcntl.LOCK_EX)
        fcntl.flock(verrou_racine, fcntl.LOCK_EX)
        chemins = (racine / ".env", racine / "gateway/.env")
        environnements = [environnement(p) for p in chemins]
        valeurs = {}
        for nom in NOMS:
            existantes = {e[nom] for e in environnements if e.get(nom)}
            if len(existantes) > 1:
                raise ValueError("Secrets incohérents ; aucune rotation automatique.")
            valeur = next(iter(existantes), None) or secrets.token_urlsafe(48)
            if not re.fullmatch(r"[A-Za-z0-9_-]{40,72}", valeur):
                raise ValueError("Secret de service invalide ; utiliser le provisionnement dédié.")
            valeurs[nom] = valeur
        if valeurs["QDRANT_API_KEY"] == valeurs["QDRANT_READ_ONLY_API_KEY"]:
            raise ValueError("Les accès lecture et administration doivent être distincts.")
        resultat = subprocess.run(
            [programme, "-niBC", "12", "platform"],
            input=valeurs["PROMETHEUS_PASSWORD"] + "\n",
            text=True,
            capture_output=True,
            check=True,
            timeout=15,
        )
        empreinte = resultat.stdout.strip().removeprefix("platform:")
        if not re.fullmatch(r"\$2[aby]\$12\$[./A-Za-z0-9]{53}", empreinte):
            raise ValueError("Empreinte bcrypt invalide.")
        fichiers = {
            "web.yml": "basic_auth_users:\n  platform: '" + empreinte + "'\n",
            "prometheus-password": valeurs["PROMETHEUS_PASSWORD"],
            "qdrant-read-key": valeurs["QDRANT_READ_ONLY_API_KEY"],
        }
        # Validate every destination before the first write; never follow links.
        for nom in fichiers:
            chemin = dossier / nom
            if chemin.is_symlink() or (chemin.exists() and not chemin.is_file()):
                raise ValueError("Destination de secret irrégulière.")
        for chemin, contenu in zip(chemins, environnements, strict=True):
            if not chemin.exists():
                with os.fdopen(os.open(chemin, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"):
                    pass
            for nom, valeur in valeurs.items():
                if contenu.get(nom) != valeur:
                    set_key(str(chemin), nom, valeur)
        for nom, contenu in fichiers.items():
            temporaire = dossier / ("." + nom + "-" + secrets.token_hex(8))
            with os.fdopen(
                os.open(temporaire, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
            ) as sortie:
                sortie.write(contenu)
                sortie.flush()
                os.fsync(sortie.fileno())
            # Host traversal stays private. Non-root containers receive only
            # individual files, never this directory or a whole environment.
            temporaire.chmod(0o644)
            temporaire.replace(dossier / nom)
        return {"services": "authentification préparée", "secrets_affiches": False}
    finally:
        os.close(fd)
        os.close(verrou_racine)


if __name__ == "__main__":
    os.umask(0o077)
    try:
        print(json.dumps(preparer(RACINE), ensure_ascii=False))
    except (OSError, ValueError, subprocess.SubprocessError) as erreur:
        print(
            json.dumps(
                {
                    "erreur": type(erreur).__name__,
                    "message": "Provisionnement interrompu ; vérifier les prérequis et fichiers privés.",
                }
            )
        )
        raise SystemExit(1) from None
