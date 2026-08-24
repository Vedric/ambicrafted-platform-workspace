"""Serveur MCP : accès aux runbooks locaux.

Sécurité : tous les accès fichier sont contraints à RUNBOOK_DIR.
Aucun chemin fourni par le modèle n'est utilisé sans validation.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from mcp.server import MCPServer

mcp = MCPServer("runbooks")

RUNBOOK_DIR = Path(os.environ.get("RUNBOOK_DIR", Path.home() / "platform" / "runbooks")).resolve()
MAX_RESULTATS = 50
MAX_TAILLE = 200_000  # octets, garde-fou contre l'épuisement de contexte


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
