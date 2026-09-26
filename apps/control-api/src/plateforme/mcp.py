"""Read-only stdio adapter. This trusted local process never approves or mutates."""

import httpx
from mcp.server import MCPServer

from .config import Parametres

serveur = MCPServer("ambicrafted-controle")


async def lire(chemin: str) -> dict | list:
    p = Parametres.charger()
    async with httpx.AsyncClient(
        base_url=p.url, timeout=15, trust_env=False, headers={"Authorization": "Bearer " + p.cle}
    ) as client:
        try:
            resultat = await client.get("/api" + chemin)
            resultat.raise_for_status()
            return resultat.json()
        except httpx.HTTPError, ValueError:
            return {"erreur": "Plan de contrôle indisponible. Vérifier le service local."}


@serveur.tool()
async def plateforme_sante() -> dict | list:
    """Consulter la santé des services locaux, sans modification."""
    return await lire("/sante")


@serveur.tool()
async def plateforme_analyses() -> dict | list:
    """Consulter les 25 analyses les plus récentes, sans approuver ni exécuter."""
    return await lire("/analyses")


@serveur.tool()
async def plateforme_runbooks() -> dict | list:
    """Consulter l'inventaire de la bibliothèque de procédures locales."""
    return await lire("/runbooks")


def main() -> None:
    serveur.run()


if __name__ == "__main__":
    main()
