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

Le script est idempotent : la collection est recréée à chaque exécution et
les identifiants de points sont déterministes (UUIDv5), donc une
réindexation ne duplique rien et ne laisse aucun fragment orphelin.

Usage :
    uv run indexer.py              # indexe
    uv run indexer.py --dry-run    # montre le découpage, sans réseau
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

# --- Configuration -------------------------------------------------------

RACINE_DEPOT = Path(__file__).resolve().parents[2]
RUNBOOK_DIR = Path(os.environ.get("RUNBOOK_DIR", RACINE_DEPOT / "runbooks")).resolve()

QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
PASSERELLE_URL = os.environ.get("LITELLM_BASE_URL", "http://localhost:4000/v1")

COLLECTION = os.environ.get("QDRANT_COLLECTION", "runbooks")
MODELE_EMBED = "local-embed"
DIMENSION = 768  # nomic-embed-text

# nomic-embed-text est entraîné avec des préfixes de tâche asymétriques :
# les documents et les requêtes ne sont pas encodés de la même manière.
# Les omettre dégrade nettement le rappel sur reformulation.
PREFIXE_DOCUMENT = "search_document: "
PREFIXE_REQUETE = "search_query: "

# Espace de noms fixe : garantit des identifiants stables entre exécutions.
NAMESPACE = uuid.UUID("3f2a7c18-5b6d-4e91-9a0c-8d4f1e2b7c63")

LOT_EMBEDDINGS = 32
DELAI_HTTP = 120.0
# nomic-embed-text a une fenêtre de 2048 jetons ; au-delà, Ollama tronque
# en silence. On alerte bien avant, en estimant ~4 caractères par jeton.
SEUIL_ALERTE_CARACTERES = 6_000

class ErreurPipeline(RuntimeError):
    """Échec actionnable du pipeline (passerelle ou Qdrant).

    Volontairement pas un SystemExit : le serveur MCP importe ce module et
    doit pouvoir rattraper l'erreur pour dégrader proprement, pas mourir.
    """


ENTETE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
CLOTURE = re.compile(r"^\s{0,3}(```|~~~)")


# --- Découpage -----------------------------------------------------------


@dataclass(frozen=True)
class Fragment:
    """Une section markdown, autoportante grâce à son chemin de titres."""

    fichier: str
    chemin_titres: str
    ligne_debut: int
    contenu: str

    @property
    def texte(self) -> str:
        """Le fragment tel qu'il est vectorisé et restitué."""
        return f"{self.chemin_titres}\n\n{self.contenu}"

    @property
    def identifiant(self) -> str:
        """UUIDv5 déterministe : réindexer écrase, ne duplique jamais."""
        graine = f"{self.fichier}:{self.ligne_debut}:{self.chemin_titres}"
        return str(uuid.uuid5(NAMESPACE, graine))


def decouper(chemin: Path) -> list[Fragment]:
    """Découpe un runbook en fragments, un par section markdown.

    Les titres situés dans un bloc de code clôturé sont ignorés : un
    commentaire shell « # ... » n'est pas un titre.
    """
    lignes = chemin.read_text(encoding="utf-8", errors="replace").splitlines()
    fragments: list[Fragment] = []

    pile: list[tuple[int, str]] = []  # (niveau, "## Titre")
    tampon: list[str] = []
    chemin_courant = ""
    ligne_courante = 1
    dans_bloc_code = False

    def vider() -> None:
        """Émet le fragment en cours s'il porte du contenu."""
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
    """Découpe tous les runbooks du répertoire, par ordre de nom."""
    fragments: list[Fragment] = []
    for f in sorted(repertoire.glob("*.md")):
        fragments.extend(decouper(f))
    return fragments


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
    """Vectorise des textes via la passerelle, par lots, ordre préservé."""
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
                    f"Passerelle injoignable ({PASSERELLE_URL}) : {e}\n"
                    "  Vérifier : cd ~/platform/gateway && docker compose ps litellm"
                ) from e

            if reponse.status_code != 200:
                raise ErreurPipeline(
                    f"Passerelle : HTTP {reponse.status_code}\n"
                    f"  Corps : {reponse.text[:300]}\n"
                    "  Vérifier l'alias 'local-embed' dans gateway/config.yaml "
                    "et les droits de la clé virtuelle."
                )

            donnees = reponse.json().get("data", [])
            if len(donnees) != len(lot):
                raise ErreurPipeline(
                    f"Réponse incohérente : {len(donnees)} vecteurs pour {len(lot)} textes."
                )
            # L'ordre est spécifié par le champ 'index' ; on ne s'en remet
            # pas à l'ordre d'arrivée.
            for element in sorted(donnees, key=lambda d: d.get("index", 0)):
                vecteurs.append(element["embedding"])

    return vecteurs


# --- Indexation ----------------------------------------------------------


def indexer(fragments: list[Fragment]) -> int:
    """Recrée la collection et y écrit tous les fragments. Idempotent."""
    vecteurs = embarquer([f.texte for f in fragments], prefixe=PREFIXE_DOCUMENT)

    largeur = len(vecteurs[0])
    if largeur != DIMENSION:
        raise ErreurPipeline(
            f"Dimension inattendue : {largeur} au lieu de {DIMENSION}.\n"
            "  L'alias 'local-embed' ne pointe probablement plus vers "
            "nomic-embed-text. Ajuster DIMENSION ou la config de la passerelle."
        )

    try:
        client = QdrantClient(url=QDRANT_URL, timeout=DELAI_HTTP)
        if client.collection_exists(COLLECTION):
            client.delete_collection(COLLECTION)
        client.create_collection(
            COLLECTION,
            vectors_config=VectorParams(size=DIMENSION, distance=Distance.COSINE),
        )
        client.upsert(
            COLLECTION,
            points=[
                PointStruct(
                    id=f.identifiant,
                    vector=v,
                    payload={
                        "fichier": f.fichier,
                        "chemin_titres": f.chemin_titres,
                        "ligne_debut": f.ligne_debut,
                        "texte": f.texte,
                    },
                )
                for f, v in zip(fragments, vecteurs, strict=True)
            ],
            wait=True,
        )
    except Exception as e:  # message actionnable, pas de trace nue
        raise ErreurPipeline(
            f"Qdrant injoignable ou en erreur ({QDRANT_URL}) : {e}\n"
            "  Vérifier : cd ~/platform/gateway && docker compose ps qdrant"
        ) from e

    return client.count(COLLECTION, exact=True).count


# --- Entrée --------------------------------------------------------------


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
        print("  Corriger : définir RUNBOOK_DIR, ou créer le répertoire.", file=sys.stderr)
        return 1

    fragments = collecter(RUNBOOK_DIR)
    if not fragments:
        print(f"Aucun fragment trouvé dans {RUNBOOK_DIR} (aucun .md ?)", file=sys.stderr)
        return 1

    fichiers = sorted({f.fichier for f in fragments})
    print(f"Source     : {RUNBOOK_DIR}")
    print(f"Runbooks   : {len(fichiers)} — {', '.join(fichiers)}")
    print(f"Fragments  : {len(fragments)}\n")

    for f in fragments:
        alerte = " ⚠ dépasse la fenêtre du modèle" if len(f.texte) > SEUIL_ALERTE_CARACTERES else ""
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
