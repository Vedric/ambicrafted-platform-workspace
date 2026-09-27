# The module docstring stays in French on purpose: it is not developer
# prose but the --help text argparse serves to an operator (see main(),
# ArgumentParser(description=__doc__)), alongside the French help= strings
# there. See the language policy in CONTRIBUTING.md.
"""Indexation sémantique des runbooks dans Qdrant.

Le découpage se fait PAR SECTION MARKDOWN, en respectant la hiérarchie des
titres, jamais par nombre de caractères : un runbook coupé au milieu d'une
procédure produit des réponses dangereuses en incident.

Chaque fragment est préfixé de son chemin de titres complet, par exemple
"# Service systemd en crash-loop > ## Diagnostic". C'est ce qui rend le
fragment interprétable hors de son document d'origine.

Les embeddings passent exclusivement par la passerelle LiteLLM (alias
"local-embed", servi par Ollama en local). Aucune donnée ne sort de la
machine, conformément à la règle 2 de CLAUDE.md : la clé virtuelle utilisée
est "confidential-only" (CONFIDENTIAL_KEY), pas la clé maître.

Chaque exécution construit une version isolée avec des identifiants de points
déterministes (UUIDv5), puis bascule l'alias après validation. Les anciennes
versions restent disponibles pour le retour arrière et nécessitent une purge
explicite par l'opérateur.

Usage :
    uv run indexer.py              # indexe
    uv run indexer.py --dry-run    # montre le découpage, sans réseau
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import (
    CreateAlias,
    CreateAliasOperation,
    DeleteAlias,
    DeleteAliasOperation,
    Distance,
    PointStruct,
    VectorParams,
)

from fichiers import lire, noms

# --- Configuration -------------------------------------------------------

RACINE_DEPOT = Path(__file__).resolve().parents[2]
RUNBOOK_DIR = Path(os.environ.get("RUNBOOK_DIR", RACINE_DEPOT / "runbooks")).resolve()

QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
PASSERELLE_URL = os.environ.get("LITELLM_BASE_URL", "http://localhost:4000/v1")

COLLECTION = os.environ.get("QDRANT_COLLECTION", "runbooks-current")
MODELE_EMBED = "local-embed"
DIMENSION = 768  # nomic-embed-text

# nomic-embed-text is trained with asymmetric task prefixes: documents and
# queries are not encoded the same way. Leaving them out clearly degrades
# recall when the question is a rephrasing.
PREFIXE_DOCUMENT = "search_document: "
PREFIXE_REQUETE = "search_query: "

# Fixed namespace: guarantees stable identifiers across runs.
NAMESPACE = uuid.UUID("3f2a7c18-5b6d-4e91-9a0c-8d4f1e2b7c63")

LOT_EMBEDDINGS = 32
DELAI_HTTP = 120.0
# nomic-embed-text has a 2048-token window; beyond that Ollama truncates
# silently. We warn well before, estimating ~4 characters per token.
SEUIL_ALERTE_CARACTERES = 6_000


class ErreurPipeline(RuntimeError):
    """An actionable pipeline failure (gateway or Qdrant).

    Deliberately not a SystemExit: the MCP server imports this module and
    has to be able to catch the error and degrade cleanly, not die.
    """


ENTETE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
CLOTURE = re.compile(r"^\s{0,3}(```|~~~)")


# --- Chunking ------------------------------------------------------------


@dataclass(frozen=True)
class Fragment:
    """One markdown section, self-contained thanks to its heading path."""

    fichier: str
    chemin_titres: str
    ligne_debut: int
    contenu: str

    @property
    def texte(self) -> str:
        """The fragment as it is embedded and returned."""
        return f"{self.chemin_titres}\n\n{self.contenu}"

    @property
    def identifiant(self) -> str:
        """Deterministic UUIDv5: reindexing overwrites, never duplicates."""
        graine = f"{self.fichier}:{self.ligne_debut}:{self.chemin_titres}"
        return str(uuid.uuid5(NAMESPACE, graine))


def decouper(chemin: Path) -> list[Fragment]:
    """Chunk a runbook into fragments, one per markdown section.

    Headings inside a fenced code block are ignored: a shell comment
    "# ..." is not a heading.
    """
    lignes = lire(chemin.parent, chemin.name).splitlines()
    fragments: list[Fragment] = []

    pile: list[tuple[int, str]] = []  # (level, "## Heading")
    tampon: list[str] = []
    chemin_courant = ""
    ligne_courante = 1
    dans_bloc_code = False

    def vider() -> None:
        """Emit the current fragment if it carries any content."""
        contenu = "\n".join(tampon).strip()
        if contenu:
            fragments.append(
                Fragment(
                    fichier=chemin.name,
                    chemin_titres=chemin_courant or f"[{chemin.name}] préambule",
                    ligne_debut=ligne_courante,
                    contenu=contenu,
                )
            )

    for i, ligne in enumerate(lignes, start=1):
        if CLOTURE.match(ligne):
            dans_bloc_code = not dans_bloc_code
            tampon.append(ligne)
            continue

        entete = None if dans_bloc_code else ENTETE.match(ligne)
        if entete is None:
            tampon.append(ligne)
            continue

        vider()

        niveau = len(entete.group(1))
        titre = entete.group(2).strip()
        while pile and pile[-1][0] >= niveau:
            pile.pop()
        pile.append((niveau, f"{'#' * niveau} {titre}"))

        chemin_courant = " > ".join(t for _, t in pile)
        ligne_courante = i
        tampon = []

    vider()
    return fragments


def collecter(repertoire: Path) -> list[Fragment]:
    """Chunk every runbook in the directory, in name order."""
    fragments: list[Fragment] = []
    for nom in noms(repertoire):
        try:
            fragments.extend(decouper(repertoire / nom))
        except OSError, ValueError:
            # Unreadable files never enter an index of trusted source reads.
            continue
    return fragments


def empreinte(fragments: list[Fragment]) -> str:
    charge = [(f.fichier, f.ligne_debut, f.texte) for f in fragments]
    return hashlib.sha256(json.dumps(charge, ensure_ascii=False).encode()).hexdigest()


# --- Embeddings ----------------------------------------------------------


def _cle_passerelle() -> str:
    cle = os.environ.get("CONFIDENTIAL_KEY", "").strip()
    if not cle:
        raise ErreurPipeline(
            "CONFIDENTIAL_KEY absente de l'environnement.\n"
            "  Corriger : lancer depuis le workspace où direnv charge .env\n"
            "  (cd ~/platform/workspace && direnv allow), puis relancer."
        )
    return cle


def embarquer(textes: list[str], *, prefixe: str) -> list[list[float]]:
    """Embed texts through the gateway, in batches, order preserved."""
    cle = _cle_passerelle()
    vecteurs: list[list[float]] = []

    with httpx.Client(timeout=DELAI_HTTP) as client:
        for debut in range(0, len(textes), LOT_EMBEDDINGS):
            lot = textes[debut : debut + LOT_EMBEDDINGS]
            try:
                reponse = client.post(
                    f"{PASSERELLE_URL}/embeddings",
                    headers={"Authorization": f"Bearer {cle}"},
                    json={"model": MODELE_EMBED, "input": [prefixe + t for t in lot]},
                )
            except httpx.HTTPError as e:
                raise ErreurPipeline(
                    f"Passerelle injoignable : {type(e).__name__}.\n"
                    "  Vérifier : cd ~/platform/workspace/gateway && docker compose ps litellm"
                ) from e

            if reponse.status_code != 200:
                raise ErreurPipeline(
                    f"Passerelle : HTTP {reponse.status_code}\n"
                    "  Vérifier l'alias 'local-embed' dans gateway/config.yaml "
                    "et les droits de la clé virtuelle."
                )

            try:
                donnees = reponse.json()["data"]
                if sorted(e["index"] for e in donnees) != list(range(len(lot))):
                    raise ValueError
                for element in sorted(donnees, key=lambda d: d["index"]):
                    vecteur = element["embedding"]
                    if (
                        len(vecteur) != DIMENSION
                        or any(
                            type(v) not in (int, float) or not math.isfinite(v)
                            for v in vecteur
                        )
                        or not any(vecteur)
                    ):
                        raise ValueError
                    vecteurs.append(vecteur)
            except ValueError, TypeError, KeyError, AttributeError:
                raise ErreurPipeline(
                    "Réponse embeddings invalide : index, dimension ou valeurs."
                ) from None

    return vecteurs


# --- Indexing ------------------------------------------------------------


def indexer(fragments: list[Fragment]) -> int:
    """Build an isolated version, validate it, then atomically switch the alias."""
    if not fragments:
        raise ErreurPipeline("Corpus vide : l'index actif est conservé.")
    if any(len(f.texte) > SEUIL_ALERTE_CARACTERES for f in fragments):
        raise ErreurPipeline(
            "Section trop longue : ajouter des sous-sections avant indexation."
        )
    vecteurs = embarquer([f.texte for f in fragments], prefixe=PREFIXE_DOCUMENT)
    if len(vecteurs) != len(fragments) or any(
        len(v) != DIMENSION or any(not math.isfinite(x) for x in v) for v in vecteurs
    ):
        raise ErreurPipeline("Nombre ou dimension des vecteurs incohérents.")
    version = f"{COLLECTION}--{uuid.uuid4().hex}"
    digest = empreinte(fragments)
    client = None
    try:
        client = QdrantClient(url=QDRANT_URL, timeout=DELAI_HTTP)
        aliases = {
            a.alias_name: a.collection_name for a in client.get_aliases().aliases
        }
        if COLLECTION not in aliases and client.collection_exists(COLLECTION):
            raise ErreurPipeline(
                "QDRANT_COLLECTION doit être un alias libre, par exemple runbooks-current. "
                "La collection historique est conservée."
            )
        client.create_collection(
            version,
            vectors_config=VectorParams(size=DIMENSION, distance=Distance.COSINE),
        )
        client.upsert(
            version,
            points=[
                PointStruct(
                    id=f.identifiant,
                    vector=v,
                    payload={
                        "fichier": f.fichier,
                        "chemin_titres": f.chemin_titres,
                        "ligne_debut": f.ligne_debut,
                        "texte": f.texte,
                        "corpus_sha256": digest,
                    },
                )
                for f, v in zip(fragments, vecteurs, strict=True)
            ],
            wait=True,
        )
        total = client.count(version, exact=True).count
        if total != len(fragments):
            raise ErreurPipeline("Index incomplet : aucune bascule de l'alias.")
        operations = []
        if COLLECTION in aliases:
            operations.append(
                DeleteAliasOperation(delete_alias=DeleteAlias(alias_name=COLLECTION))
            )
        operations.append(
            CreateAliasOperation(
                create_alias=CreateAlias(alias_name=COLLECTION, collection_name=version)
            )
        )
        client.update_collection_aliases(change_aliases_operations=operations)
        return total
    except ErreurPipeline:
        raise
    except Exception as e:  # noqa: BLE001 — redact arbitrary SDK failures at the CLI boundary.
        raise ErreurPipeline(
            f"Réindexation interrompue ({type(e).__name__}). "
            "L'index précédent n'est jamais supprimé. Vérifier l'alias avant de nettoyer les versions."
        ) from None
    finally:
        if client is not None:
            with contextlib.suppress(Exception):
                client.close()


# --- Entry point ---------------------------------------------------------


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument(
        "--dry-run",
        action="store_true",
        help="affiche le découpage sans appeler la passerelle ni Qdrant",
    )
    options = analyseur.parse_args()

    if not RUNBOOK_DIR.is_dir():
        print(f"Répertoire de runbooks absent : {RUNBOOK_DIR}", file=sys.stderr)
        print(
            "  Corriger : définir RUNBOOK_DIR, ou créer le répertoire.", file=sys.stderr
        )
        return 1

    try:
        fragments = collecter(RUNBOOK_DIR)
    except OSError, ValueError:
        print("Corpus inaccessible ou limites de lecture dépassées.", file=sys.stderr)
        return 1
    if not fragments:
        print(
            f"Aucun fragment trouvé dans {RUNBOOK_DIR} (aucun .md ?)", file=sys.stderr
        )
        return 1

    fichiers = sorted({f.fichier for f in fragments})
    print(f"Source     : {RUNBOOK_DIR}")
    print(f"Runbooks   : {len(fichiers)} ({', '.join(fichiers)})")
    print(f"Fragments  : {len(fragments)}\n")

    for f in fragments:
        alerte = (
            " ⚠ dépasse la fenêtre du modèle"
            if len(f.texte) > SEUIL_ALERTE_CARACTERES
            else ""
        )
        print(f"  {f.fichier}:{f.ligne_debut:>3}  ({len(f.texte):>4} car.){alerte}")
        print(f"      {f.chemin_titres}")

    if options.dry_run:
        print("\n[--dry-run] Aucun appel réseau, aucune écriture.")
        return 0

    print(f"\nVectorisation via {PASSERELLE_URL} (modèle {MODELE_EMBED})…")
    try:
        total = indexer(fragments)
    except ErreurPipeline as e:
        print(f"\n{e}", file=sys.stderr)
        return 1
    print(f"Collection '{COLLECTION}' sur {QDRANT_URL} : {total} points.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
