"""Accès aux outils du serveur MCP runbooks.

Garde-fou structurel : c'est le SEUL fournisseur d'outils de l'agent. Il
n'y a pas de shell, pas d'écriture fichier, pas d'appel HTTP arbitraire,
et ce n'est pas parce qu'un prompt l'interdit — c'est parce qu'aucune
fonction de ce paquet ne les expose au modèle. La sécurité vient de
l'absence de l'outil.

Seconde couche : OUTILS_AUTORISES est une liste blanche fermée. Un outil
que le serveur viendrait à publier sans figurer ici ne serait jamais
présenté au modèle. Ajouter un outil est une décision de ce fichier,
jamais une conséquence d'une mise à jour du serveur.

Le serveur MCP est asynchrone, la boucle de l'agent est synchrone et
délibérément lisible. On isole donc l'asynchrone dans un fil dédié qui
tient la session ouverte, et on expose une façade synchrone.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import threading
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any, Self

from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp.client.stdio import get_default_environment
from opentelemetry.trace import Status, StatusCode

from . import config, tracage

# Liste blanche fermée. Les quatre outils du serveur runbooks sont en
# lecture seule : ils listent, lisent et cherchent. Aucun n'écrit.
OUTILS_AUTORISES = frozenset(
    {"list_runbooks", "read_runbook", "search_runbooks", "semantic_search"}
)

# Un résultat d'outil est une donnée non fiable qui entre dans le
# contexte : on le borne pour qu'un runbook anormalement gros ne chasse
# pas les instructions du contexte.
MAX_RESULTAT_OUTIL = 12_000


class ErreurOutil(RuntimeError):
    """Le serveur d'outils est inutilisable."""


@dataclass(frozen=True)
class Outil:
    nom: str
    description: str
    schema: dict[str, Any]

    def format_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.nom,
                "description": self.description,
                "parameters": self.schema,
            },
        }


class ClientRunbooks:
    """Session MCP vers le serveur runbooks, façade synchrone.

    S'utilise en gestionnaire de contexte : le sous-processus du serveur
    est démarré à l'entrée et arrêté à la sortie, y compris sur
    exception.
    """

    def __init__(self) -> None:
        self._boucle: asyncio.AbstractEventLoop | None = None
        self._fil: threading.Thread | None = None
        self._pret = threading.Event()
        self._erreur: BaseException | None = None
        self._arret: asyncio.Event | None = None
        self.outils: list[Outil] = []
        self.outils_ecartes: list[str] = []

    # --- Cycle de vie ----------------------------------------------------

    def __enter__(self) -> Self:
        self._fil = threading.Thread(target=self._demarrer_boucle, daemon=True)
        self._fil.start()
        if not self._pret.wait(timeout=120):
            raise ErreurOutil("Le serveur MCP runbooks n'a pas démarré en 120 s.")
        if self._erreur is not None:
            raise ErreurOutil(
                f"Serveur MCP runbooks indisponible : {_cause(self._erreur)}\n"
                f"Vérifier : cd {config.MCP_RUNBOOKS_DIR} && uv run server.py"
            ) from self._erreur
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._boucle and self._arret and not self._boucle.is_closed():
            self._boucle.call_soon_threadsafe(self._arret.set)
        if self._fil:
            self._fil.join(timeout=30)

    def _demarrer_boucle(self) -> None:
        # Le serveur MCP journalise en clair sur stderr. En incident, ce
        # flux noie la sortie de l'agent : on le détourne, sauf demande
        # explicite de diagnostic. Le fichier est ouvert ici, hors de la
        # boucle d'événements, qu'une ouverture bloquante figerait.
        try:
            with contextlib.ExitStack() as pile:
                if os.environ.get("SRE_DEBUG_MCP"):
                    journal: Any = sys.stderr
                else:
                    journal = pile.enter_context(open(os.devnull, "w"))
                asyncio.run(self._piloter(journal))
        except BaseException as e:  # noqa: BLE001 — remontée au fil appelant
            self._erreur = e
        finally:
            self._pret.set()

    async def _piloter(self, journal: Any) -> None:
        """Tient la session MCP ouverte et sert les appels du fil principal.

        La session est un gestionnaire de contexte asynchrone : elle doit
        vivre dans une seule coroutine. On ne peut donc pas ouvrir puis
        rendre la main — d'où cette boucle de service.
        """
        self._boucle = asyncio.get_running_loop()
        self._arret = asyncio.Event()
        self._demandes: asyncio.Queue[tuple[str, dict[str, Any], Future[str]]] = (
            asyncio.Queue()
        )

        parametres = StdioServerParameters(
            command="uv",
            args=["run", "--directory", config.MCP_RUNBOOKS_DIR, "server.py"],
            # Le serveur a besoin du chemin des runbooks, de la passerelle
            # et de CONFIDENTIAL_KEY : sa recherche sémantique vectorise
            # la requête via l'alias local-embed. La requête de recherche
            # ne quitte donc pas la machine elle non plus.
            env=get_default_environment()
            | {
                nom: valeur
                for nom, valeur in (
                    ("RUNBOOK_DIR", config.RUNBOOK_DIR),
                    ("LITELLM_BASE_URL", config.LITELLM_BASE_URL),
                    ("CONFIDENTIAL_KEY", config.cle(config.Classification.CONFIDENTIEL)),
                    ("QDRANT_URL", config.QDRANT_URL),
                )
                if valeur
            },
        )

        async with (
            stdio_client(parametres, errlog=journal) as (lecture, ecriture),
            ClientSession(lecture, ecriture) as session,
        ):
            await session.initialize()
            publies = (await session.list_tools()).tools
            for outil in publies:
                if outil.name in OUTILS_AUTORISES:
                    self.outils.append(
                        Outil(
                            nom=outil.name,
                            description=(outil.description or "").strip(),
                            schema=outil.input_schema or {"type": "object"},
                        )
                    )
                else:
                    self.outils_ecartes.append(outil.name)
            self._pret.set()

            while True:
                attente_arret = asyncio.ensure_future(self._arret.wait())
                attente_demande = asyncio.ensure_future(self._demandes.get())
                fini, _ = await asyncio.wait(
                    {attente_arret, attente_demande},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if attente_arret in fini:
                    attente_demande.cancel()
                    return
                attente_arret.cancel()
                nom, arguments, promesse = attente_demande.result()
                try:
                    resultat = await session.call_tool(nom, arguments)
                    promesse.set_result(_texte(resultat))
                except BaseException as e:  # noqa: BLE001 — rendu à l'appelant
                    promesse.set_exception(e)

    # --- Façade synchrone -------------------------------------------------

    def outils_openai(self) -> list[dict[str, Any]]:
        """Déclaration des outils au format attendu par la passerelle."""
        return [o.format_openai() for o in self.outils]

    def appeler(self, nom: str, arguments: dict[str, Any]) -> str:
        """Exécute un outil. Refuse tout nom hors liste blanche."""
        if nom not in OUTILS_AUTORISES:
            return (
                f"Refusé : '{nom}' n'est pas un outil de cet agent. "
                f"Outils disponibles : {sorted(OUTILS_AUTORISES)}."
            )
        if self._boucle is None or self._arret is None:
            raise ErreurOutil("Session MCP fermée.")

        promesse: Future[str] = Future()
        self._boucle.call_soon_threadsafe(
            self._demandes.put_nowait, (nom, arguments, promesse)
        )
        texte = promesse.result(timeout=180)
        if len(texte) > MAX_RESULTAT_OUTIL:
            texte = texte[:MAX_RESULTAT_OUTIL] + (
                f"\n\n[TRONQUÉ par l'agent à {MAX_RESULTAT_OUTIL} caractères]"
            )
        return texte


def _cause(e: BaseException) -> str:
    """Déplie un groupe d'exceptions anyio jusqu'à la cause réelle.

    Sans cela, toute panne du serveur MCP se présente comme « unhandled
    errors in a TaskGroup », ce qui n'aide personne à 3 h du matin.
    """
    while isinstance(e, BaseExceptionGroup) and e.exceptions:
        e = e.exceptions[0]
    return f"{type(e).__name__} : {e}"


def _texte(resultat: Any) -> str:
    """Aplatit un CallToolResult en texte."""
    morceaux: list[str] = []
    for bloc in getattr(resultat, "content", None) or []:
        valeur = getattr(bloc, "text", None)
        if valeur:
            morceaux.append(valeur)
    if getattr(resultat, "isError", False):
        return "ERREUR OUTIL : " + ("\n".join(morceaux) or "erreur non détaillée")
    return "\n".join(morceaux)


def executer_outil(
    client: ClientRunbooks, nom: str, arguments: dict[str, Any], budget: Any
) -> str:
    """Exécute un outil sous budget et sous span.

    Le budget est décompté AVANT l'exécution : un appel refusé faute de
    budget n'atteint jamais le serveur.
    """
    budget.consommer_outil(nom)
    with tracage.tracer().start_as_current_span(f"tool.{nom}") as span:
        span.set_attribute(tracage.ATTR_OUTIL_SOURCE, "mcp:runbooks")
        span.set_attribute(tracage.ATTR_TYPE_TACHE, "tool_call")
        # Les runbooks sont notre documentation, pas de la donnée client.
        span.set_attribute(tracage.ATTR_CLASSIFICATION, "derive")
        span.set_attribute("mcp.tool.name", nom)
        span.set_attribute("mcp.tool.arguments", str(arguments)[:500])
        span.set_attribute(tracage.ATTR_BUDGET_OUTILS, budget.appels_outils)
        try:
            resultat = client.appeler(nom, arguments)
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise
        span.set_attribute("mcp.tool.result_chars", len(resultat))
        return resultat
