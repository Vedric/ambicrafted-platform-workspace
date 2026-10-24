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
import hashlib
import json
import os
import sys
import threading
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
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
        self._noms_distants: dict[str, str] = {}
        self.delai = 180.0
        self._tache: asyncio.Task | None = None

    # --- Life cycle ------------------------------------------------------

    def __enter__(self) -> Self:
        self._fil = threading.Thread(target=self._demarrer_boucle, daemon=True)
        self._fil.start()
        if not self._pret.wait(timeout=120):
            self.__exit__()
            raise ErreurOutil("Le serveur MCP runbooks n'a pas démarré en 120 s.")
        if self._erreur is not None:
            self.__exit__()
            raise ErreurOutil(
                f"Serveur MCP runbooks indisponible : {_cause(self._erreur)}\n"
                "Vérifier la préparation locale et l'installation de la passerelle MCP."
            ) from self._erreur
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._boucle and self._arret and not self._boucle.is_closed():
            self._boucle.call_soon_threadsafe(self._arret.set)
            if self._tache:
                self._boucle.call_soon_threadsafe(self._tache.cancel)
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
        self._tache = asyncio.current_task()
        self._arret = asyncio.Event()
        self._demandes: asyncio.Queue[tuple[str, dict[str, Any], Future[str]]] = asyncio.Queue()

        parametres = StdioServerParameters(
            command=os.environ.get(
                "SRE_UV_BIN",
                str(Path.home() / ".local/bin/uv")
                if (Path.home() / ".local/bin/uv").is_file()
                else "uv",
            ),
            args=[
                "run",
                "--locked",
                "--project",
                config.MCP_PASSERELLE_PROJET,
                "python",
                "-m",
                "plateforme.passerelle",
                "--profil",
                "runbooks",
            ],
            # The server needs the runbooks path, the gateway and
            # CONFIDENTIAL_KEY: its semantic search embeds the query
            # through the local-embed alias. So the search query does not
            # leave the machine either.
            env=get_default_environment()
            | {
                nom: valeur
                for nom, valeur in (
                    ("PLATFORM_ROOT", config.RACINE_DEPOT),
                    ("RUNBOOK_DIR", config.RUNBOOK_DIR),
                    ("LITELLM_BASE_URL", config.LITELLM_BASE_URL),
                    ("CONFIDENTIAL_KEY", config.cle(config.Classification.CONFIDENTIEL)),
                    ("QDRANT_URL", config.QDRANT_URL),
                    ("QDRANT_READ_ONLY_API_KEY", config.QDRANT_READ_ONLY_API_KEY),
                    ("QDRANT_COLLECTION", config.QDRANT_COLLECTION),
                    ("LANGSMITH_TRACING", "false"),
                    ("LANGCHAIN_TRACING_V2", "false"),
                )
                if valeur
            },
        )

        async with (
            stdio_client(parametres, errlog=journal) as (lecture, ecriture),
            ClientSession(lecture, ecriture) as session,
        ):
            await asyncio.wait_for(session.initialize(), timeout=110)
            publies = (await session.list_tools()).tools
            for outil in publies:
                nom = outil.name.removeprefix("runbooks__")
                if outil.name.startswith("runbooks__") and nom in OUTILS_AUTORISES:
                    self._noms_distants[nom] = outil.name
                    self.outils.append(
                        Outil(
                            nom=nom,
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
                    resultat = await asyncio.wait_for(
                        session.call_tool(self._noms_distants[nom], arguments), self.delai
                    )
                    if not promesse.done():
                        promesse.set_result(_texte(resultat))
                except BaseException as e:
                    if not promesse.done():
                        promesse.set_exception(e)
                    if isinstance(e, asyncio.CancelledError):
                        raise

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
        self._boucle.call_soon_threadsafe(self._demandes.put_nowait, (nom, arguments, promesse))
        try:
            texte = promesse.result(timeout=self.delai)
        except Exception as e:  # noqa: BLE001 — redact arbitrary MCP transport exceptions.
            promesse.cancel()
            raise ErreurOutil(f"Appel MCP interrompu : {type(e).__name__}.") from None
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
    return type(e).__name__


def _texte(resultat: Any) -> str:
    """Flatten a CallToolResult into text."""
    morceaux: list[str] = []
    for bloc in getattr(resultat, "content", None) or []:
        valeur = getattr(bloc, "text", None)
        if valeur:
            morceaux.append(valeur)
    if getattr(resultat, "is_error", False) or getattr(resultat, "isError", False):
        raise ErreurOutil("Le serveur MCP a signalé une erreur ; détails masqués.")
    return "\n".join(morceaux)


def executer_outil(client: ClientRunbooks, nom: str, arguments: dict[str, Any], budget: Any) -> str:
    """Run a tool under budget and under a span.

    The budget is charged BEFORE execution: a call refused for lack of
    budget never reaches the server.
    """
    if nom not in OUTILS_AUTORISES:
        raise ErreurOutil("Outil hors de la liste autorisée.")
    budget.consommer_outil(nom)
    from .progression import signaler

    signaler("outil")
    client.delai = min(180.0, budget.temps_restant())
    with tracage.tracer().start_as_current_span(
        f"tool.{nom}", record_exception=False, set_status_on_exception=False
    ) as span:
        span.set_attribute(tracage.ATTR_OUTIL_SOURCE, "mcp:runbooks")
        span.set_attribute(tracage.ATTR_TYPE_TACHE, "tool_call")
        # Search arguments and returned passages remain confidential.
        span.set_attribute(tracage.ATTR_CLASSIFICATION, "confidentiel")
        span.set_attribute("mcp.tool.name", nom)
        span.set_attribute(tracage.ATTR_BUDGET_OUTILS, budget.appels_outils)
        try:
            resultat = client.appeler(nom, arguments)
        except Exception as e:  # noqa: BLE001 — tool failures must not disclose their payload.
            span.set_status(Status(StatusCode.ERROR, type(e).__name__))
            raise ErreurOutil(f"Échec de l'outil {nom} : {type(e).__name__}.") from None
        budget.temps_restant()
        if nom == "read_runbook":
            _memoriser_source(resultat, arguments, budget.sources_lues)
        span.set_attribute("mcp.tool.result_chars", len(resultat))
        return resultat


def _memoriser_source(resultat: str, arguments: dict, sources: dict[str, str]) -> None:
    """Accept only a complete, versioned read envelope from our MCP server."""
    try:
        lecture = json.loads(resultat)
        nom, texte = lecture["fichier"], lecture["texte"]
        if (
            nom != arguments.get("nom")
            or not isinstance(nom, str)
            or not nom.endswith(".md")
            or "/" in nom
            or "\\" in nom
            or nom.startswith(".")
            or not isinstance(texte, str)
            or lecture.get("tronque") is not False
            or lecture.get("sha256") != hashlib.sha256(texte.encode()).hexdigest()
        ):
            return
        sources[nom] = texte
    except ValueError, TypeError, KeyError, AttributeError:
        return
