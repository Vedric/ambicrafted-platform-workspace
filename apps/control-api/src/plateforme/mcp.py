"""Read-only stdio adapter. This trusted local process never approves or mutates."""

import asyncio
import re
from typing import Annotated, Literal

import httpx
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from .config import Parametres
from .corpus import Corpus
from .services import json_borne

serveur = MCPServer("ambicrafted-controle")
LECTURE = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
ERREUR = {"erreur": "Plan de contrôle indisponible. Vérifier le service local."}


async def lire(chemin: str, params: dict | None = None) -> dict | list:
    try:
        p = Parametres.charger(lecture_seule=True)
        async with (
            asyncio.timeout(40),
            httpx.AsyncClient(
                base_url=p.url,
                timeout=35,
                trust_env=False,
                follow_redirects=False,
                headers={"Authorization": "Bearer " + p.cle},
            ) as client,
        ):
            resultat = await json_borne(client, "GET", "/api" + chemin, params=params)
            if not isinstance(resultat, dict | list):
                return ERREUR.copy()
            return resultat
    except httpx.HTTPError, ValueError, OSError, TimeoutError:
        return ERREUR.copy()


@serveur.tool(annotations=LECTURE)
async def plateforme_sante() -> dict | list:
    """Consulter la santé des services locaux, sans modification."""
    return await lire("/sante")


@serveur.tool(annotations=LECTURE)
async def plateforme_analyses() -> dict | list:
    """Consulter les 25 analyses les plus récentes, sans approuver ni exécuter."""
    return await lire("/analyses")


@serveur.tool(annotations=LECTURE)
async def plateforme_runbooks() -> dict | list:
    """Consulter l'inventaire de la bibliothèque de procédures locales."""
    return await lire("/runbooks")


@serveur.tool(annotations=LECTURE)
async def plateforme_analyse(
    identifiant: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")],
) -> dict | list:
    """Lire une analyse existante et sa proposition, sans changer son état."""
    if not re.fullmatch(r"[a-f0-9]{32}", identifiant):
        return {"erreur": "Identifiant invalide."}
    return await lire("/analyses/" + identifiant)


@serveur.tool(annotations=LECTURE)
async def plateforme_lire_runbook(
    nom: Annotated[str, Field(min_length=4, max_length=119)],
) -> dict | list:
    """Lire un fichier Markdown local avec son empreinte pour vérifier une source."""
    try:
        Corpus.verifier(nom)
    except ValueError:
        return {"erreur": "Nom de runbook invalide."}
    return await lire("/runbooks/" + nom)


@serveur.tool(annotations=LECTURE)
async def plateforme_recherche(
    requete: Annotated[str, Field(min_length=2, max_length=500)],
    mode: Literal["texte", "semantique"] = "texte",
) -> dict | list:
    """Rechercher des procédures : texte exact ou embeddings locaux, sans données distantes."""
    if not 2 <= len(requete.strip()) <= 500 or mode not in {"texte", "semantique"}:
        return {"erreur": "Recherche invalide."}
    return await lire("/recherche", {"q": requete, "mode": mode})


@serveur.tool(annotations=LECTURE)
async def plateforme_preparation() -> dict | list:
    """Diagnostiquer les capacités locales mesurées ; ce résultat ne certifie pas la production."""
    return await lire("/preparation")


@serveur.tool(annotations=LECTURE)
async def plateforme_outils() -> dict | list:
    """Lire le catalogue explicite des outils et leurs limites de lecture seule."""
    return await lire("/outils")


@serveur.tool(annotations=LECTURE)
async def plateforme_journal(limite: Annotated[int, Field(ge=1, le=100)] = 20) -> dict | list:
    """Lire au plus 100 événements d'audit récents, sans contenu des alertes ni secrets."""
    if type(limite) is not int or not 1 <= limite <= 100:
        return {"erreur": "Limite invalide."}
    return await lire("/journal", {"limite": limite})


def main() -> None:
    serveur.run()


if __name__ == "__main__":
    main()
