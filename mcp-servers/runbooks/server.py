"""Serveur MCP : accès aux runbooks locaux.

Sécurité : tous les accès fichier sont contraints à RUNBOOK_DIR.
Aucun chemin fourni par le modèle n'est utilisé sans validation.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from mcp.server import MCPServer

mcp = MCPServer("runbooks")

RUNBOOK_DIR = Path(os.environ.get("RUNBOOK_DIR", Path.home() / "platform" / "runbooks")).resolve()
MAX_RESULTATS = 50
MAX_TAILLE = 200_000  # octets, garde-fou contre l'épuisement de contexte
MAX_K = 20            # plafond de fragments sémantiques par appel
MAX_EXTRAIT = 4_000   # caractères par fragment restitué

# Import gardé : list_runbooks, read_runbook et search_runbooks doivent
# rester utilisables même si la brique RAG est absente ou cassée. Une
# dépendance manquante ne doit jamais empêcher le serveur de démarrer.
try:
    # indexer.py est un module frère, pas un paquet installé : selon le
    # lanceur (uv run server.py, mcp dev), son répertoire n'est pas
    # toujours sur sys.path.
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
except Exception as _e:  # noqa: BLE001 — un import raté ne tue pas le serveur
    _RAG_ERREUR = f"{type(_e).__name__} : {_e}"

_REPLI = (
    "Repli immédiat : search_runbooks(terme=...) ne dépend ni de Qdrant ni "
    "de la passerelle, elle reste disponible."
)


def _resoudre(nom: str) -> Path:
    """Résout un nom de fichier en refusant toute sortie du répertoire."""
    if "/" in nom or "\\" in nom or nom.startswith("."):
        raise ValueError("Nom de fichier invalide.")
    chemin = (RUNBOOK_DIR / nom).resolve()
    if not chemin.is_relative_to(RUNBOOK_DIR):
        raise ValueError("Accès hors périmètre refusé.")
    return chemin


@mcp.tool()
def list_runbooks() -> str:
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
    except Exception as e:  # noqa: BLE001 — dégrader, jamais lever
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
    except Exception as e:  # noqa: BLE001 — dégrader, jamais lever
        return (
            f"Qdrant injoignable sur {QDRANT_URL} : {type(e).__name__} : {e}\n"
            "Corriger : cd ~/platform/gateway && docker compose up -d qdrant\n"
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

        # Le nom de fichier vient de la charge utile Qdrant, donc de
        # l'extérieur du processus : on le valide avant de le proposer,
        # puisque le modèle le repassera probablement à read_runbook.
        brut = str(charge.get("fichier", "?"))
        try:
            _resoudre(brut)
            fichier = brut
        except ValueError:
            fichier = f"{brut!r} [nom invalide, ne pas passer à read_runbook]"

        ligne = charge.get("ligne_debut", "?")
        # 'texte' porte déjà son chemin de titres en préfixe : c'est ce qui
        # rend le fragment lisible hors de son document.
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
    """Index de tous les runbooks, injectable comme contexte."""
    return list_runbooks()


@mcp.prompt()
def diagnostic(symptome: str) -> str:
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
