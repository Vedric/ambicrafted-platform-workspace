"""MCP server: access to the local runbooks.

Security: every file access is confined to RUNBOOK_DIR. No path supplied
by the model is used without validation.

Language note: the docstrings of the @mcp.tool, @mcp.resource and
@mcp.prompt functions below stay in French. They are not developer prose:
MCP publishes them as the tool, resource and prompt descriptions, so a
model reads them, not a developer, and `outils.py` copies them straight
into the payload sent to the gateway. SYSTEME_RAISONNEMENT, which is in
French, describes those same tools. See the language policy in
CONTRIBUTING.md.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from mcp.server import MCPServer

mcp = MCPServer("runbooks")

# Default: <repository root>/runbooks, derived from this file's location
# (same mechanism as indexer.py); RUNBOOK_DIR still takes precedence.
RACINE_DEPOT = Path(__file__).resolve().parents[2]
RUNBOOK_DIR = Path(os.environ.get("RUNBOOK_DIR", RACINE_DEPOT / "runbooks")).resolve()
MAX_RESULTATS = 50
MAX_TAILLE = 200_000  # bytes, guardrail against context exhaustion
MAX_K = 20            # ceiling on semantic fragments per call
MAX_EXTRAIT = 4_000   # characters per returned fragment

# Guarded import: list_runbooks, read_runbook and search_runbooks must stay
# usable even when the RAG part is absent or broken. A missing dependency
# must never stop the server from starting.
try:
    # indexer.py is a sibling module, not an installed package: depending
    # on the launcher (uv run server.py, mcp dev), its directory is not
    # always on sys.path.
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    from qdrant_client import QdrantClient

    from indexer import (
        COLLECTION,
        PREFIXE_REQUETE,
        QDRANT_URL,
        ErreurPipeline,
        embarquer,
    )

    _RAG_ERREUR = ""
except Exception as _e:  # noqa: BLE001 (a failed import does not kill the server)
    _RAG_ERREUR = f"{type(_e).__name__} : {_e}"

_REPLI = (
    "Repli immédiat : search_runbooks(terme=...) ne dépend ni de Qdrant ni "
    "de la passerelle, elle reste disponible."
)


def _resoudre(nom: str) -> Path:
    """Resolve a file name, refusing any escape from the directory."""
    if "/" in nom or "\\" in nom or nom.startswith("."):
        raise ValueError("Nom de fichier invalide.")
    chemin = (RUNBOOK_DIR / nom).resolve()
    if not chemin.is_relative_to(RUNBOOK_DIR):
        raise ValueError("Accès hors périmètre refusé.")
    return chemin


@mcp.tool()
def list_runbooks() -> str:
    # French on purpose: MCP publishes this as the tool description.
    """Liste les runbooks disponibles avec leur titre et leur taille."""
    if not RUNBOOK_DIR.exists():
        return f"Répertoire absent : {RUNBOOK_DIR}"

    lignes = []
    for f in sorted(RUNBOOK_DIR.glob("*.md")):
        texte = f.read_text(encoding="utf-8", errors="replace")
        premiere = texte.splitlines()[:1]
        titre = premiere[0].lstrip("# ").strip() if premiere else f.stem
        lignes.append(f"{f.name} ({len(texte)} car.) : {titre}")

    return "\n".join(lignes) if lignes else "Aucun runbook."


@mcp.tool()
def read_runbook(nom: str) -> str:
    # French on purpose: MCP publishes this as the tool description.
    """Lit un runbook complet.

    Args:
        nom: nom du fichier seul, par exemple 'incident-p1-database.md'
    """
    try:
        chemin = _resoudre(nom)
    except ValueError as e:
        return f"Refusé : {e}"

    if not chemin.exists():
        return f"Introuvable : {nom}. Utiliser list_runbooks pour voir les noms."

    texte = chemin.read_text(encoding="utf-8", errors="replace")
    if len(texte) > MAX_TAILLE:
        return texte[:MAX_TAILLE] + f"\n\n[TRONQUÉ à {MAX_TAILLE} caractères]"
    return texte


@mcp.tool()
def search_runbooks(terme: str, contexte: int = 2) -> str:
    # French on purpose: MCP publishes this as the tool description.
    """Cherche un terme dans tous les runbooks.

    Args:
        terme: chaîne ou expression régulière à chercher
        contexte: nombre de lignes affichées avant et après chaque occurrence
    """
    try:
        motif = re.compile(terme, re.IGNORECASE)
    except re.error as e:
        return f"Expression invalide : {e}"

    resultats: list[str] = []
    for f in sorted(RUNBOOK_DIR.glob("*.md")):
        lignes = f.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, ligne in enumerate(lignes):
            if motif.search(ligne):
                debut = max(0, i - contexte)
                fin = min(len(lignes), i + contexte + 1)
                extrait = "\n".join(f"  {lignes[j]}" for j in range(debut, fin))
                resultats.append(f"--- {f.name}:{i+1} ---\n{extrait}")
                if len(resultats) >= MAX_RESULTATS:
                    return "\n\n".join(resultats) + "\n\n[Limite atteinte, affiner la recherche]"

    return "\n\n".join(resultats) if resultats else f"Aucun résultat pour '{terme}'."


@mcp.tool()
def semantic_search(requete: str, k: int = 5) -> str:
    # French on purpose: MCP publishes this as the tool description.
    """Cherche dans les runbooks par le sens, pas par les mots.

    Complémentaire de search_runbooks, les deux ne se remplacent pas :
    - search_runbooks (regex) est imbattable sur un terme exact : code
      d'erreur, nom de service, chemin de fichier.
    - semantic_search retrouve le bon runbook quand la question le
      reformule, par exemple « redémarre en boucle » pour « crash-loop ».

    En doute, appeler les deux.

    Args:
        requete: la question, en langage naturel
        k: nombre de fragments retournés, de 1 à 20
    """
    requete = requete.strip()
    if not requete:
        return "Requête vide. Fournir une question en langage naturel."

    if not isinstance(k, int) or k < 1:
        k = 5
    k = min(k, MAX_K)

    if _RAG_ERREUR:
        return (
            f"Recherche sémantique indisponible, dépendance manquante ({_RAG_ERREUR}).\n"
            f"Corriger : cd {Path(__file__).resolve().parent} && uv sync\n"
            f"{_REPLI}"
        )

    try:
        vecteur = embarquer([requete], prefixe=PREFIXE_REQUETE)[0]
    except ErreurPipeline as e:
        return f"Vectorisation de la requête impossible.\n{e}\n{_REPLI}"
    except Exception as e:  # noqa: BLE001 (degrade, never raise)
        return (
            f"Vectorisation de la requête impossible : {type(e).__name__} : {e}\n"
            f"{_REPLI}"
        )

    try:
        client = QdrantClient(url=QDRANT_URL, timeout=30.0)
        if not client.collection_exists(COLLECTION):
            return (
                f"Collection '{COLLECTION}' absente : les runbooks ne sont pas "
                "encore indexés.\n"
                f"Corriger : cd {Path(__file__).resolve().parent} && uv run indexer.py\n"
                f"{_REPLI}"
            )
        points = client.query_points(
            COLLECTION, query=vecteur, limit=k, with_payload=True
        ).points
    except Exception as e:  # noqa: BLE001 (degrade, never raise)
        return (
            f"Qdrant injoignable sur {QDRANT_URL} : {type(e).__name__} : {e}\n"
            "Corriger : cd ~/platform/workspace/gateway && docker compose up -d qdrant\n"
            f"{_REPLI}"
        )

    if not points:
        return (
            f"Aucun fragment pertinent pour '{requete}'.\n"
            "Reformuler avec le vocabulaire d'exploitation, ou utiliser "
            "search_runbooks pour un terme exact."
        )

    blocs: list[str] = []
    total = 0
    for rang, point in enumerate(points, start=1):
        charge = point.payload or {}

        # The file name comes from the Qdrant payload, so from outside the
        # process: it is validated before being offered, since the model
        # will most likely hand it straight back to read_runbook.
        brut = str(charge.get("fichier", "?"))
        try:
            _resoudre(brut)
            fichier = brut
        except ValueError:
            fichier = f"{brut!r} [nom invalide, ne pas passer à read_runbook]"

        ligne = charge.get("ligne_debut", "?")
        # 'texte' already carries its heading path as a prefix: that is
        # what makes the fragment readable outside its document.
        texte = str(charge.get("texte") or charge.get("chemin_titres", ""))
        if len(texte) > MAX_EXTRAIT:
            texte = texte[:MAX_EXTRAIT] + f"\n[TRONQUÉ à {MAX_EXTRAIT} caractères]"

        bloc = f"--- #{rang} score {point.score:.3f} | {fichier}:{ligne} ---\n{texte}"
        if total + len(bloc) > MAX_TAILLE:
            blocs.append(
                f"[Arrêt après {rang - 1} fragments : plafond de {MAX_TAILLE} "
                "caractères atteint. Relancer avec un k plus petit.]"
            )
            break
        blocs.append(bloc)
        total += len(bloc)

    return "\n\n".join(blocs)


@mcp.resource("runbook://index")
def index() -> str:
    # French on purpose: MCP publishes this as the resource description.
    """Index de tous les runbooks, injectable comme contexte."""
    return list_runbooks()


@mcp.prompt()
def diagnostic(symptome: str) -> str:
    # French on purpose: MCP publishes this as the prompt description.
    """Modèle de diagnostic guidé à partir d'un symptôme observé."""
    return f"""Symptôme observé : {symptome}

Procède ainsi :
1. Appelle search_runbooks pour trouver les runbooks pertinents
2. Lis les runbooks trouvés avec read_runbook
3. Établis la liste des vérifications à faire, dans l'ordre
4. Signale explicitement ce que les runbooks NE couvrent PAS

Ne propose aucune action de remédiation sans citer le runbook
qui la fonde, ou sans dire clairement qu'elle n'est pas documentée."""


if __name__ == "__main__":
    mcp.run()
