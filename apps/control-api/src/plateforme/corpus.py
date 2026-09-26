"""Human-owned Markdown editing with confined reads and optimistic concurrency."""

import hashlib
import os
import re
import secrets
import stat
import threading
from pathlib import Path

from .depot import Conflit, Depot, Introuvable, maintenant


class Corpus:
    def __init__(self, racine: Path, depot: Depot):
        self.racine, self.depot = racine, depot
        self.verrou = threading.RLock()

    @staticmethod
    def verifier(nom: str) -> None:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,115}\.md", nom):
            raise ValueError("Nom attendu : lettres, chiffres, tirets et extension .md.")

    def lire(self, nom: str) -> dict:
        self.verifier(nom)
        racine = os.open(self.racine, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            try:
                fd = os.open(nom, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=racine)
            except FileNotFoundError:
                raise Introuvable("Runbook introuvable.") from None
            with os.fdopen(fd, "rb") as fichier:
                if not stat.S_ISREG(os.fstat(fichier.fileno()).st_mode):
                    raise ValueError("Runbook non régulier.")
                contenu = fichier.read(32_001)
                if len(contenu) > 32_000:
                    raise ValueError("Runbook trop volumineux pour l'éditeur.")
                texte = contenu.decode("utf-8")
                return {
                    "nom": nom,
                    "contenu": texte,
                    "empreinte": hashlib.sha256(contenu).hexdigest(),
                    "titre": next(
                        (l.lstrip("# ") for l in texte.splitlines() if l.startswith("# ")), nom
                    ),
                    "octets": len(contenu),
                }
        finally:
            os.close(racine)

    def lister(self, recherche: str = "") -> list[dict]:
        resultats = []
        with os.scandir(self.racine) as entrees:
            for i, entree in enumerate(entrees):
                if i >= 1000:
                    raise ValueError("Corpus trop volumineux.")
                if not entree.name.endswith(".md") or not entree.is_file(follow_symlinks=False):
                    continue
                document = self.lire(entree.name)
                if recherche.casefold() in (document["contenu"] + document["nom"]).casefold():
                    document["extrait"] = document["contenu"][:240]
                    del document["contenu"]
                    resultats.append(document)
        return sorted(resultats, key=lambda r: r["nom"])

    def ecrire(self, nom: str, contenu: str, empreinte: str, acteur: str) -> dict:
        self.verifier(nom)
        if not contenu.strip() or len(contenu) > 8000 or len(contenu.encode()) > 32000:
            raise ValueError("Un runbook doit contenir entre 1 et 8 000 caractères.")
        with self.verrou:
            try:
                actuel = self.lire(nom)
            except Introuvable:
                actuel = None
            if (actuel and actuel["empreinte"] != empreinte) or (not actuel and empreinte):
                raise Conflit(
                    "Ce runbook a changé. Recharger sa dernière version avant d'enregistrer."
                )
            racine = os.open(self.racine, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            temporaire = ".edition-" + secrets.token_hex(12)
            try:
                fd = os.open(temporaire, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600, dir_fd=racine)
                with os.fdopen(fd, "wb") as fichier:
                    fichier.write(contenu.encode())
                    fichier.flush()
                    os.fsync(fichier.fileno())
                # Same-directory replace cannot follow a final-component symlink.
                os.replace(temporaire, nom, src_dir_fd=racine, dst_dir_fd=racine)
                os.fsync(racine)
            finally:
                try:
                    os.unlink(temporaire, dir_fd=racine)
                except FileNotFoundError:
                    pass
                os.close(racine)
            if actuel:
                with self.depot.connexion() as c:
                    c.execute(
                        "INSERT INTO revisions(nom,date,empreinte,contenu) VALUES(?,?,?,?)",
                        (nom, maintenant(), actuel["empreinte"], actuel["contenu"]),
                    )
                    c.execute(
                        "DELETE FROM revisions WHERE nom=? AND id NOT IN "
                        "(SELECT id FROM revisions WHERE nom=? ORDER BY id DESC LIMIT 10)",
                        (nom, nom),
                    )
            self.depot.auditer("runbook.enregistre", nom, acteur)
            return self.lire(nom)
