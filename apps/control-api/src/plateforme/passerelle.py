"""One bounded stdio gateway for the repository's two trusted, local MCP backends.

This is an authority boundary, not an OS sandbox. Backend processes run as the
same trusted local operator. No dynamic command, URL, plugin or tool discovery
can enlarge the fixed inventory below.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from anyio import CancelScope
from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from .config import lire_environnement
from .stdio_posix import entree_stdio, sortie_stdio

OUTILS_RUNBOOKS = frozenset({"list_runbooks", "read_runbook", "search_runbooks", "semantic_search"})
OUTILS_CONTROLE = frozenset(
    {
        "plateforme_sante",
        "plateforme_analyses",
        "plateforme_runbooks",
        "plateforme_analyse",
        "plateforme_lire_runbook",
        "plateforme_recherche",
        "plateforme_preparation",
        "plateforme_outils",
        "plateforme_journal",
        "plateforme_memoire",
        "plateforme_note_memoire",
    }
)
AUTORISES = {"runbooks": OUTILS_RUNBOOKS, "controle": OUTILS_CONTROLE}
MAX_ARGUMENTS = 16_384
MAX_RESULTAT = 1_000_000
MAX_INVENTAIRE = 65_536
DELAI_DEMARRAGE = 15.0
DELAI_APPEL = 125.0


def erreur(message: str) -> CallToolResult:
    return CallToolResult(is_error=True, content=[TextContent(type="text", text=message)])


def locale(url: str) -> bool:
    try:
        cible = urlsplit(url)
        return (
            cible.scheme == "http"
            and cible.hostname in {"localhost", "127.0.0.1", "::1"}
            and cible.username is None
            and cible.password is None
            and not cible.query
            and not cible.fragment
        )
    except ValueError:
        return False


@dataclass(frozen=True)
class ConfigurationBackend:
    nom: str
    processus: StdioServerParameters


def configurations(profil: str = "complet") -> list[ConfigurationBackend]:
    if profil not in {"complet", "runbooks", "controle"}:
        raise ValueError("Profil MCP inconnu.")
    racine = Path(os.environ.get("PLATFORM_ROOT", Path(__file__).resolve().parents[4])).resolve()
    # The restricted agent profile receives its already-filtered environment;
    # it does not load the control plane's .env or pass its key to a child.
    valeurs = lire_environnement(racine) if profil == "complet" else {}
    valeurs.update(os.environ)
    base = {k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "LANG", "TMPDIR"}}
    base.update(LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false", PYTHONUNBUFFERED="1")
    resultat = []
    if profil in {"complet", "runbooks"}:
        env = base | {
            "RUNBOOK_DIR": valeurs.get("RUNBOOK_DIR", str(racine / "runbooks")),
            "LITELLM_BASE_URL": valeurs.get("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1"),
            "QDRANT_URL": valeurs.get("QDRANT_URL", "http://127.0.0.1:6333"),
            "QDRANT_COLLECTION": valeurs.get("QDRANT_COLLECTION", "runbooks-current"),
        }
        if not locale(env["LITELLM_BASE_URL"]) or not locale(env["QDRANT_URL"]):
            raise ValueError("Les services MCP doivent rester sur la boucle locale.")
        if valeurs.get("CONFIDENTIAL_KEY"):
            env["CONFIDENTIAL_KEY"] = valeurs["CONFIDENTIAL_KEY"]
        resultat.append(
            ConfigurationBackend(
                "runbooks",
                StdioServerParameters(
                    command=str(racine / "mcp-servers/runbooks/.venv/bin/python"),
                    args=[str(racine / "mcp-servers/runbooks/server.py")],
                    env=env,
                    cwd=str(racine),
                ),
            )
        )
    if profil in {"complet", "controle"}:
        env = base | {"PLATFORM_ROOT": str(racine)}
        for nom in ("PLATFORM_STATE_DIR", "PLATFORM_PORT"):
            if valeurs.get(nom):
                env[nom] = valeurs[nom]
        resultat.append(
            ConfigurationBackend(
                "controle",
                StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "plateforme.mcp"],
                    env=env,
                    cwd=str(racine),
                ),
            )
        )
    return resultat


class Backend:
    def __init__(self, configuration: ConfigurationBackend):
        self.configuration = configuration
        self.session: ClientSession | None = None
        self.outils: dict[str, Tool] = {}
        self.pret = asyncio.Event()
        self.arret = asyncio.Event()
        self.occupe = False
        self.echec = False

    async def servir(self) -> None:
        """Keep every SDK context in its owning task, including its cleanup."""
        try:
            with open(os.devnull, "w") as journal:  # noqa: ASYNC230 - fixed null device.
                async with (
                    stdio_client(self.configuration.processus, errlog=journal) as (
                        lecture,
                        ecriture,
                    ),
                    ClientSession(
                        lecture, ecriture, read_timeout_seconds=DELAI_DEMARRAGE
                    ) as session,
                ):
                    async with asyncio.timeout(DELAI_DEMARRAGE):
                        await session.initialize()
                        inventaire = await session.list_tools()
                    if inventaire.next_cursor or len(inventaire.tools) > 32:
                        raise ValueError("Inventaire MCP hors limite.")
                    if len(inventaire.model_dump_json().encode()) > MAX_INVENTAIRE:
                        raise ValueError("Métadonnées MCP hors limite.")
                    noms = [o.name for o in inventaire.tools]
                    if len(set(noms)) != len(noms):
                        raise ValueError("Inventaire MCP ambigu.")
                    for outil in inventaire.tools:
                        if outil.name not in AUTORISES[self.configuration.nom]:
                            continue
                        a = outil.annotations
                        if not a or a.read_only_hint is not True or a.destructive_hint is not False:
                            raise ValueError("Un outil ne respecte plus son contrat de lecture.")
                        if a.open_world_hint is not False or outil.execution is not None:
                            raise ValueError("Capacité MCP non autorisée.")
                        public = self.configuration.nom + "__" + outil.name
                        # Keep schemas and standard annotations. Do not proxy arbitrary
                        # icons, URLs, extension metadata, resources or task capabilities.
                        self.outils[public] = Tool(
                            name=public,
                            title=outil.title,
                            description=outil.description,
                            input_schema=outil.input_schema,
                            output_schema=outil.output_schema,
                            annotations=a.model_copy(deep=True),
                        )
                    self.session = session
                    self.pret.set()
                    await self.arret.wait()
        except Exception:  # noqa: BLE001 - never expose backend errors, paths or credentials.
            self.echec = True
        finally:
            self.session = None
            self.outils.clear()
            self.pret.set()


class Passerelle:
    def __init__(self, definitions: list[ConfigurationBackend]):
        noms = [d.nom for d in definitions]
        if len(noms) != len(set(noms)) or not set(noms) <= AUTORISES.keys():
            raise ValueError("Backends MCP inconnus ou ambigus.")
        self.backends = {d.nom: Backend(d) for d in definitions}

    @contextlib.asynccontextmanager
    async def ouvrir(self, _serveur: Any):
        taches = [asyncio.create_task(b.servir()) for b in self.backends.values()]
        try:
            await asyncio.gather(*(b.pret.wait() for b in self.backends.values()))
            yield self
        finally:
            # Keep cleanup in each backend's owning task. Shield the join from
            # repeated AnyIO level cancellation after a broken client transport.
            with CancelScope(shield=True):
                for backend, tache in zip(self.backends.values(), taches, strict=True):
                    backend.arret.set()
                    # Initialization has no active session yet and may be waiting
                    # for a backend that never replies. Cancel it once so its SDK
                    # contexts perform their bounded process-tree cleanup now.
                    if backend.session is None and not tache.done():
                        tache.cancel()
                await asyncio.gather(*taches, return_exceptions=True)

    async def lister(self, _contexte: Any, params: Any) -> ListToolsResult:
        if params is not None and params.cursor:
            return ListToolsResult(tools=[])
        return ListToolsResult(
            tools=[
                outil.model_copy(deep=True)
                for backend in self.backends.values()
                for outil in backend.outils.values()
            ]
        )

    async def appeler(self, _contexte: Any, params: Any) -> CallToolResult:
        namespace, separateur, nom = params.name.partition("__")
        backend = self.backends.get(namespace)
        if not separateur or not backend or nom not in AUTORISES[namespace]:
            return erreur("Outil hors de la liste autorisée.")
        if backend.session is None or params.name not in backend.outils:
            return erreur("Backend MCP indisponible. Vérifier la préparation locale.")
        arguments = params.arguments or {}
        try:
            taille = len(json.dumps(arguments, ensure_ascii=False, allow_nan=False).encode())
        except ValueError, TypeError, RecursionError:
            return erreur("Arguments MCP invalides.")
        if taille > MAX_ARGUMENTS:
            return erreur("Arguments MCP trop volumineux.")
        if backend.occupe:
            return erreur("Backend MCP occupé. Réessayer après l'appel en cours.")
        backend.occupe = True
        try:
            async with asyncio.timeout(DELAI_APPEL):
                resultat = await backend.session.call_tool(
                    nom, arguments, read_timeout_seconds=DELAI_APPEL + 1
                )
            if not isinstance(resultat, CallToolResult) or resultat.is_error:
                return erreur("L'outil MCP a échoué ; détails internes masqués.")
            if len(resultat.model_dump_json().encode()) > MAX_RESULTAT:
                return erreur("Résultat MCP trop volumineux.")
            if any(bloc.type != "text" for bloc in resultat.content):
                return erreur("Type de résultat MCP non autorisé.")
            return resultat
        except TimeoutError:
            backend.arret.set()
            return erreur("Délai MCP dépassé. Relancer la connexion locale.")
        except Exception:  # noqa: BLE001 - transport exceptions can contain private data.
            return erreur("Appel MCP interrompu ; détails internes masqués.")
        finally:
            backend.occupe = False

    async def executer(self) -> None:
        serveur = Server(
            "ambicrafted-passerelle",
            title="NEXUS · Passerelle MCP locale",
            version="1.0.0",
            lifespan=self.ouvrir,
            on_list_tools=self.lister,
            on_call_tool=self.appeler,
            instructions="Outils locaux de lecture seule. Aucun outil d'exécution ni d'approbation.",
        )
        boucle = asyncio.get_running_loop()
        tache = asyncio.current_task()
        fermeture = False

        def terminer() -> None:
            nonlocal fermeture
            if not fermeture:
                fermeture = True
                if tache:
                    tache.cancel()

        boucle.add_signal_handler(signal.SIGTERM, terminer)
        try:
            async with (
                entree_stdio() as entree,
                sortie_stdio() as sortie,
                stdio_server(stdin=entree, stdout=sortie) as (lecture, ecriture),
            ):
                await serveur.run(lecture, ecriture, serveur.create_initialization_options())
        except asyncio.CancelledError:
            if not fermeture:
                raise
        finally:
            boucle.remove_signal_handler(signal.SIGTERM)


def main() -> None:
    parseur = argparse.ArgumentParser(description="Passerelle MCP locale privée, transport stdio.")
    parseur.add_argument("--profil", choices=["complet", "runbooks", "controle"], default="complet")
    args = parseur.parse_args()
    # Protocol stdout only; third-party logs can contain returned private data.
    logging.disable(logging.CRITICAL)
    try:
        asyncio.run(Passerelle(configurations(args.profil)).executer())
    except KeyboardInterrupt:
        pass
    except Exception:  # noqa: BLE001 - process failures must not dump configuration.
        print("Passerelle MCP indisponible. Vérifier l'installation locale.", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
