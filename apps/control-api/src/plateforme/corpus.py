"""Human-owned Markdown editing with confined reads and optimistic concurrency."""

import hashlib
import json
import os
import re
import secrets
import stat
import threading
from dataclasses import dataclass
from pathlib import Path

from .depot import Conflit, Depot, Introuvable, maintenant

# Versioned runbook index contract; tested against the indexer's actual parser.
MAX_OCTETS_INDEX = 200_000
MAX_ENTREES_INDEX = 1_000
# API verification keeps two snapshots. Bound aggregate work and Markdown
# heading expansion independently of the indexer's per-file limits.
MAX_OCTETS_CORPUS = 8_000_000
MAX_CARACTERES_FRAGMENTS = 8_000_000
MAX_FRAGMENTS_INDEX = 10_000
ENTETE_INDEX = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
CLOTURE_INDEX = re.compile(r"^\s{0,3}(```|~~~)")


@dataclass(frozen=True)
class FragmentIndex:
    fichier: str
    chemin_titres: str
    ligne_debut: int
    texte: str


@dataclass(frozen=True)
class InstantaneIndex:
    empreinte: str
    fragments: dict[tuple[str, int], FragmentIndex]
    revision: tuple


@dataclass
class _BudgetIndex:
    octets: int = 0
    caracteres: int = 0
    fragments: int = 0

    def fragment(self, taille: int) -> None:
        self.caracteres += taille
        self.fragments += 1
        if self.caracteres > MAX_CARACTERES_FRAGMENTS or self.fragments > MAX_FRAGMENTS_INDEX:
            raise ValueError("Corpus trop volumineux pour vérifier la provenance.")


def _revision(info: os.stat_result) -> tuple[int, ...]:
    # ctime also detects an edit followed by restoration of the original bytes.
    # Reading a file may update atime; that is deliberately not a mutation.
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_gid,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _fragments_index(nom: str, texte: str, budget: _BudgetIndex) -> list[FragmentIndex]:
    """Preserve the indexer's heading, fence, preamble and whitespace semantics."""
    fragments: list[FragmentIndex] = []
    pile: list[tuple[int, str]] = []
    tampon: list[str] = []
    chemin_courant, ligne_courante, dans_code = "", 1, False

    def vider() -> None:
        contenu = "\n".join(tampon).strip()
        if contenu:
            titres = chemin_courant or f"[{nom}] préambule"
            budget.fragment(len(titres) + 2 + len(contenu))
            fragments.append(FragmentIndex(nom, titres, ligne_courante, f"{titres}\n\n{contenu}"))

    for numero, ligne in enumerate(texte.splitlines(), start=1):
        if CLOTURE_INDEX.match(ligne):
            dans_code = not dans_code
            tampon.append(ligne)
            continue
        entete = None if dans_code else ENTETE_INDEX.match(ligne)
        if entete is None:
            tampon.append(ligne)
            continue
        vider()
        niveau = len(entete.group(1))
        while pile and pile[-1][0] >= niveau:
            pile.pop()
        pile.append((niveau, f"{'#' * niveau} {entete.group(2).strip()}"))
        chemin_courant = " > ".join(titre for _, titre in pile)
        ligne_courante, tampon = numero, []
    vider()
    return fragments


def instantane_index(repertoire: Path) -> InstantaneIndex:
    """Read a bounded, confined corpus, failing closed on observed mutations.

    Like the indexer, skip unreadable/nonregular/oversized Markdown files and
    decode invalid UTF-8 with replacement. Repository files need not be private;
    the OS enforces read permissions. Never follow symlinks or block on FIFOs.
    """
    racine = os.open(repertoire, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        revision_racine = _revision(os.fstat(racine))
        noms: list[str] = []
        with os.scandir(racine) as entrees:
            for numero, entree in enumerate(entrees, start=1):
                if numero > MAX_ENTREES_INDEX:
                    raise ValueError("Corpus trop volumineux : au plus 1 000 entrées.")
                if entree.name.endswith(".md") and not entree.name.startswith("."):
                    noms.append(entree.name)
        revisions: dict[str, tuple[int, ...]] = {}
        fragments: list[FragmentIndex] = []
        budget = _BudgetIndex()
        for nom in sorted(noms):
            avant = os.stat(nom, dir_fd=racine, follow_symlinks=False)
            revisions[nom] = _revision(avant)
            if "\\" in nom or not stat.S_ISREG(avant.st_mode) or avant.st_size > MAX_OCTETS_INDEX:
                continue
            budget.octets += avant.st_size
            if budget.octets > MAX_OCTETS_CORPUS:
                raise ValueError("Corpus trop volumineux pour vérifier la provenance.")
            try:
                fd = os.open(nom, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=racine)
            except OSError:
                # The indexer excludes unreadable files. A concurrent removal
                # still fails the final metadata checks below.
                continue
            with os.fdopen(fd, "rb") as fichier:
                if _revision(os.fstat(fd)) != revisions[nom]:
                    raise ValueError("Le corpus a changé pendant sa lecture.")
                contenu = fichier.read(MAX_OCTETS_INDEX + 1)
                if _revision(os.fstat(fd)) != revisions[nom]:
                    raise ValueError("Le corpus a changé pendant sa lecture.")
                if len(contenu) > MAX_OCTETS_INDEX:
                    continue
            fragments.extend(
                _fragments_index(nom, contenu.decode("utf-8", errors="replace"), budget)
            )

        for nom, revision in revisions.items():
            if _revision(os.stat(nom, dir_fd=racine, follow_symlinks=False)) != revision:
                raise ValueError("Le corpus a changé pendant sa lecture.")
        if (
            _revision(os.fstat(racine)) != revision_racine
            or _revision(os.stat(repertoire, follow_symlinks=False)) != revision_racine
        ):
            raise ValueError("Le corpus a changé pendant sa lecture.")

        charge = [(f.fichier, f.ligne_debut, f.texte) for f in fragments]
        empreinte = hashlib.sha256()
        # Exact default JSON spacing is part of the published index contract.
        # Stream encoding rather than allocate another entire corpus string.
        for bloc in json.JSONEncoder(ensure_ascii=False).iterencode(charge):
            empreinte.update(bloc.encode())
        return InstantaneIndex(
            empreinte.hexdigest(),
            {(f.fichier, f.ligne_debut): f for f in fragments},
            (revision_racine, tuple(revisions.items())),
        )
    finally:
        os.close(racine)


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
