"""Access to the runbooks MCP server tools.

Structural guardrail: this is the ONLY tool provider the agent has. There
is no shell, no file write, no arbitrary HTTP call, and not because a
prompt forbids them, but because no function in this package exposes them
to the model. The security comes from the tool being absent.

Second layer: OUTILS_AUTORISES is a closed allowlist. A tool the server
started publishing without being listed here would never be presented to
the model. Adding a tool is a decision made in this file, never a
consequence of a server update.

The MCP server is asynchronous, the agent loop is synchronous and
deliberately readable. So the asynchronous part is confined to a dedicated
thread that holds the session open, behind a synchronous facade.
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

# Closed allowlist. The four tools of the runbooks server are read-only:
# they list, read and search. None of them writes.
OUTILS_AUTORISES = frozenset(
    {"list_runbooks", "read_runbook", "search_runbooks", "semantic_search"}
)

# A tool result is untrusted data entering the context: it is bounded so
# that an abnormally large runbook cannot push the instructions out of
# that context.
MAX_RESULTAT_OUTIL = 12_000


class ErreurOutil(RuntimeError):
    """The tool server is unusable."""


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
    """MCP session to the runbooks server, behind a synchronous facade.

    Used as a context manager: the server subprocess is started on entry
    and stopped on exit, including on an exception.
    """

    def __init__(self) -> None:
        self._boucle: asyncio.AbstractEventLoop | None = None
        self._fil: threading.Thread | None = None
        self._pret = threading.Event()
        self._erreur: BaseException | None = None
        self._arret: asyncio.Event | None = None
        self.outils: list[Outil] = []
        self.outils_ecartes: list[str] = []

    # --- Life cycle ------------------------------------------------------

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
        # The MCP server logs in the clear on stderr. During an incident
        # that stream drowns the agent's output, so it is diverted unless
        # diagnosis is explicitly asked for. The file is opened here,
        # outside the event loop, which a blocking open would freeze.
        try:
            with contextlib.ExitStack() as pile:
                if os.environ.get("SRE_DEBUG_MCP"):
                    journal: Any = sys.stderr
                else:
                    journal = pile.enter_context(open(os.devnull, "w"))
                asyncio.run(self._piloter(journal))
        except BaseException as e:  # noqa: BLE001 (handed back to the calling thread)
            self._erreur = e
        finally:
            self._pret.set()

    async def _piloter(self, journal: Any) -> None:
        """Hold the MCP session open and serve calls from the main thread.

        The session is an async context manager: it has to live inside a
        single coroutine. So one cannot open it and then hand control
        back: hence this service loop.
        """
        self._boucle = asyncio.get_running_loop()
        self._arret = asyncio.Event()
        self._demandes: asyncio.Queue[tuple[str, dict[str, Any], Future[str]]] = (
            asyncio.Queue()
        )

        parametres = StdioServerParameters(
            command="uv",
            args=["run", "--directory", config.MCP_RUNBOOKS_DIR, "server.py"],
            # The server needs the runbooks path, the gateway and
            # CONFIDENTIAL_KEY: its semantic search embeds the query
            # through the local-embed alias. So the search query does not
            # leave the machine either.
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
                except BaseException as e:  # noqa: BLE001 (returned to the caller)
                    promesse.set_exception(e)

    # --- Synchronous facade -----------------------------------------------

    def outils_openai(self) -> list[dict[str, Any]]:
        """Tool declarations in the shape the gateway expects."""
        return [o.format_openai() for o in self.outils]

    def appeler(self, nom: str, arguments: dict[str, Any]) -> str:
        """Run a tool. Refuses any name outside the allowlist."""
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
    """Unwrap an anyio exception group down to the real cause.

    Without this, every MCP server failure shows up as "unhandled errors
    in a TaskGroup", which helps nobody at 3 a.m.
    """
    while isinstance(e, BaseExceptionGroup) and e.exceptions:
        e = e.exceptions[0]
    return f"{type(e).__name__} : {e}"


def _texte(resultat: Any) -> str:
    """Flatten a CallToolResult into text."""
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
    """Run a tool under budget and under a span.

    The budget is charged BEFORE execution: a call refused for lack of
    budget never reaches the server.
    """
    budget.consommer_outil(nom)
    with tracage.tracer().start_as_current_span(f"tool.{nom}") as span:
        span.set_attribute(tracage.ATTR_OUTIL_SOURCE, "mcp:runbooks")
        span.set_attribute(tracage.ATTR_TYPE_TACHE, "tool_call")
        # The runbooks are our documentation, not customer data.
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
