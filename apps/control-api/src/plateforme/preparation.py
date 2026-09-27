"""Bounded, read-only evidence for this workstation; never a production certificate."""

import asyncio
import copy
import importlib.metadata
import ipaddress
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from mcp import ClientSession, StdioServerParameters, stdio_client

from .config import Parametres, lire_environnement
from .corpus import Corpus
from .services import Services, json_borne
from .voix import Voix

CACHE_SECONDES = 30
DELAI_SONDE = 20
LIMITES = [
    "This is local operational readiness, not a security or production certification.",
    "One trusted operator on this workstation; remote access and tenant isolation are not supported.",
    "No client content is sent to a model by these checks. Inference quality and load are not tested.",
    "Dependency vulnerabilities, recovery objectives and client acceptance require separate review.",
    "Voice checks verify installed model files, not microphone permission or speaker hardware.",
]


def controle(
    identifiant: str,
    groupe: str,
    statut: str,
    label: str,
    message: str,
    *,
    requis: bool = True,
    preuve: dict | None = None,
    commande: str = "",
) -> dict:
    return {
        "id": identifiant,
        "group": groupe,
        "status": statut,
        "required": requis,
        "label": label,
        "message": message,
        "evidence": preuve or {},
        "action": {"label": "Run locally after review", "command": commande} if commande else None,
    }


def prive(chemin: Path, *, dossier: bool = False) -> bool:
    try:
        infos = chemin.lstat()
        return (
            not chemin.is_symlink()
            and (chemin.is_dir() if dossier else chemin.is_file())
            and infos.st_uid == os.getuid()
            and not infos.st_mode & 0o077
        )
    except OSError:
        return False


def boucle_locale(url: str) -> bool:
    try:
        cible = urlsplit(url)
        return (
            cible.scheme == "http"
            and cible.hostname in {"127.0.0.1", "localhost", "::1"}
            and cible.username is None
            and cible.password is None
            and not cible.query
            and not cible.fragment
        )
    except ValueError:
        return False


def ecoutes_locales(port: int) -> list[bool]:
    """Read Linux socket tables, never shell output, process arguments or environments."""
    observations = []
    for nom in ("tcp", "tcp6"):
        chemin = Path("/proc/net") / nom
        if nom == "tcp6" and not chemin.exists():
            continue
        with chemin.open("r", encoding="ascii") as fichier:
            texte = fichier.read(1_000_001)
        if len(texte) > 1_000_000:
            raise ValueError("Socket table exceeds the diagnostic bound.")
        for ligne in texte.splitlines()[1:]:
            champs = ligne.split()
            if len(champs) < 4 or champs[3] != "0A":
                continue
            adresse, numero = champs[1].split(":")
            if int(numero, 16) != port:
                continue
            octets = bytes.fromhex(adresse)
            # Linux prints native-endian 32-bit words, also for IPv6.
            if sys.byteorder == "little":
                octets = b"".join(octets[i : i + 4][::-1] for i in range(0, len(octets), 4))
            observations.append(ipaddress.ip_address(octets).is_loopback)
    return observations


async def inventorier_mcp(executable: str, arguments: list[str], env: dict[str, str]) -> set[str]:
    """Initialize actual stdio transport and list tools; never call a tool or inherit secrets."""
    with open(os.devnull, "w") as journal:  # noqa: ASYNC230 - fixed local null device, never user I/O.
        async with (
            stdio_client(
                StdioServerParameters(command=executable, args=arguments, env=env), errlog=journal
            ) as (lecture, ecriture),
            ClientSession(lecture, ecriture) as session,
        ):
            await session.initialize()
            outils = (await session.list_tools()).tools
            if len(outils) > 100:
                raise ValueError("Unexpected tool inventory.")
            return {o.name for o in outils}


class Preparation:
    def __init__(self, p: Parametres, services: Services, voix: Voix, corpus: Corpus):
        self.p, self.services, self.voix, self.corpus = p, services, voix, corpus
        self.cache: dict = {}
        self.date = 0.0
        self.verrou = asyncio.Lock()

    async def verifier(self) -> dict:
        async with self.verrou:
            if self.cache and time.monotonic() - self.date < CACHE_SECONDES:
                return copy.deepcopy(self.cache)
            debut = time.monotonic()
            groupes = await asyncio.gather(
                self.borne("runtime", self.runtime),
                self.borne("configuration", self.configuration),
                self.borne("configuration_listener", self.ecoute),
                self.borne("services", self.demons),
                self.borne("routing", self.routage),
                self.borne("knowledge", self.connaissance),
                self.borne("voice_en", lambda: self.vocal("en"), requis=False),
                self.borne("voice_fr", lambda: self.vocal("fr"), requis=False),
                self.borne("mcp_control", lambda: self.mcp("control")),
                self.borne("mcp_runbooks", lambda: self.mcp("runbooks")),
            )
            checks = [c for groupe in groupes for c in groupe]
            succes = {c["id"] for c in checks if c["status"] == "pass"}
            analyse = {
                "runtime_agent",
                "configuration_private",
                "configuration_local",
                "configuration_listener",
                "service_litellm",
                "service_ollama",
                "routing_aliases",
                "knowledge_sources",
                "mcp_runbooks",
            } <= succes
            self.cache = {
                "schema_version": 1,
                "checked_at": datetime.now(UTC).isoformat(),
                "duration_ms": round((time.monotonic() - debut) * 1000),
                "scope": "local-private",
                "ready": all(c["status"] == "pass" for c in checks if c["required"]),
                "summary": {
                    s: sum(c["status"] == s for c in checks)
                    for s in ("pass", "warn", "fail", "unknown")
                },
                "checks": checks,
                "capabilities": {
                    "analysis": analyse,
                    "semantic_search": analyse and {"service_qdrant", "knowledge_index"} <= succes,
                    "voice_en": "voice_en" in succes,
                    "voice_fr": "voice_fr" in succes,
                    "mcp_readonly": {"mcp_control", "mcp_runbooks"} <= succes,
                },
                "limits": LIMITES,
            }
            self.date = time.monotonic()
            return copy.deepcopy(self.cache)

    async def borne(self, identifiant, fonction, *, requis=True) -> list[dict]:
        try:
            async with asyncio.timeout(DELAI_SONDE):
                return await fonction()
        except Exception:  # noqa: BLE001 - probe errors may contain credentials or local paths.
            return [
                controle(
                    identifiant,
                    identifiant.split("_")[0],
                    "unknown",
                    "Check unavailable",
                    "The bounded local check did not complete. Retry after checking the local service.",
                    requis=requis,
                )
            ]

    async def runtime(self) -> list[dict]:
        versions = {}
        for paquet in ("fastapi", "httpx", "mcp", "sre-agent", "uvicorn"):
            try:
                versions[paquet] = importlib.metadata.version(paquet)[:40]
            except importlib.metadata.PackageNotFoundError:
                versions[paquet] = "missing"
        agent = self.p.racine / "agents/sre-agent/.venv/bin/sre-agent-graph"
        executable = agent.is_file() and os.access(agent, os.X_OK)
        web = (self.p.web / "index.html").is_file()
        return [
            controle(
                "runtime_api",
                "runtime",
                "pass" if "missing" not in versions.values() else "fail",
                "Control runtime",
                "Installed package metadata in the running API process.",
                preuve={"packages": versions, "python": ".".join(map(str, sys.version_info[:3]))},
            ),
            controle(
                "runtime_agent",
                "runtime",
                "pass" if executable else "fail",
                "Analysis executable",
                "The installed graph entrypoint is executable."
                if executable
                else "Install the locked agent environment.",
                preuve={"executable": executable},
                commande="uv sync --locked --project agents/sre-agent --extra graphe",
            ),
            controle(
                "runtime_ui",
                "runtime",
                "pass" if web else "fail",
                "Console build",
                "The console entrypoint exists." if web else "Build the console before opening it.",
                preuve={"entrypoint": web},
                commande="npm --prefix apps/console run build",
            ),
        ]

    async def configuration(self) -> list[dict]:
        secret = prive(self.p.racine / ".env")
        etat = prive(self.p.etat, dossier=True)
        env = lire_environnement(self.p.racine)
        local = (
            all(
                boucle_locale(env.get(cle, valeur))
                for cle, valeur in {
                    "LITELLM_BASE_URL": "http://127.0.0.1:4000/v1",
                    "QDRANT_URL": "http://127.0.0.1:6333",
                    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318",
                }.items()
            )
            and not self.p.origine_dev
        )
        return [
            controle(
                "configuration_private",
                "configuration",
                "pass" if secret and etat else "fail",
                "Private storage",
                "Owner-only environment and state permissions are checked without exposing their contents.",
                preuve={"environment_private": secret, "state_private": etat},
            ),
            controle(
                "configuration_local",
                "configuration",
                "pass" if local else "fail",
                "Local connection policy",
                "Agent HTTP destinations use loopback and development cross-origin access is disabled."
                if local
                else "An agent destination or development origin is outside the private production policy.",
                preuve={
                    "loopback_destinations": local,
                    "cross_origin_development": bool(self.p.origine_dev),
                },
            ),
        ]

    async def ecoute(self) -> list[dict]:
        ecoutes = await asyncio.to_thread(ecoutes_locales, self.p.port)
        ok = bool(ecoutes) and all(ecoutes)
        return [
            controle(
                "configuration_listener",
                "configuration",
                "pass" if ok else "fail" if ecoutes else "unknown",
                "Private API listener",
                "All observed listeners on the configured API port use loopback."
                if ok
                else "The configured API port has no observed listener or includes a non-loopback binding.",
                preuve={"listener_count": len(ecoutes), "loopback_only": ok},
            )
        ]

    async def demons(self) -> list[dict]:
        sante = await self.services.sante()
        observations = {s["id"]: s for s in sante["services"]}
        checks = []
        for nom in ("litellm", "ollama", "qdrant", "prometheus", "tempo", "grafana"):
            service = observations.get(nom, {})
            ok = service.get("ok") is True
            requis = nom in {"litellm", "ollama", "qdrant"}
            checks.append(
                controle(
                    "service_" + nom,
                    "services",
                    "pass" if ok else "fail" if requis else "warn",
                    nom.capitalize(),
                    "The fixed local HTTP health endpoint responds."
                    if ok
                    else "The local health endpoint is unavailable.",
                    requis=requis,
                    preuve={"reachable": ok},
                    commande="./plateforme statut",
                )
            )
        index = sante.get("index", {})
        points = index.get("points", 0)
        disponible = index.get("statut") == "green" and isinstance(points, int) and points > 0
        checks.append(
            controle(
                "knowledge_index",
                "knowledge",
                "pass" if disponible else "warn",
                "Semantic index",
                "The local runbooks index is green and contains vectors."
                if disponible
                else "The local runbooks index is empty, unavailable or not green.",
                requis=False,
                preuve={"populated": disponible},
                commande="./plateforme operation indexer",
            )
        )
        return checks

    async def routage(self) -> list[dict]:
        env = lire_environnement(self.p.racine)
        cle = env.get("CONFIDENTIAL_KEY", "")
        if not cle:
            return [
                controle(
                    "routing_aliases",
                    "routing",
                    "fail",
                    "Confidential routing",
                    "The confidential local-only credential is missing.",
                )
            ]
        # Always use the fixed loopback gateway, never a URL supplied by the caller or .env.
        async with httpx.AsyncClient(timeout=4, trust_env=False, follow_redirects=False) as client:
            resultat = await json_borne(
                client,
                "GET",
                "http://127.0.0.1:4000/v1/models",
                headers={"Authorization": "Bearer " + cle},
            )
        donnees = resultat.get("data")
        if not isinstance(donnees, list) or len(donnees) > 100:
            raise ValueError("Invalid model inventory.")
        alias = {
            m.get("id") for m in donnees if isinstance(m, dict) and isinstance(m.get("id"), str)
        }
        ok = alias == {"local", "local-embed"}
        return [
            controle(
                "routing_aliases",
                "routing",
                "pass" if ok else "fail",
                "Confidential routing",
                "The credential's live model inventory contains exactly the two local aliases. Provider routing still requires configuration review."
                if ok
                else "The credential's live inventory does not match the two permitted local aliases.",
                preuve={
                    "local": "local" in alias,
                    "local_embed": "local-embed" in alias,
                    "unexpected_aliases": len(alias - {"local", "local-embed"}),
                },
            )
        ]

    async def connaissance(self) -> list[dict]:
        # Only a count leaves this check, never runbook titles, excerpts or client data.
        total = len(await asyncio.to_thread(self.corpus.lister))
        return [
            controle(
                "knowledge_sources",
                "knowledge",
                "pass" if total else "fail",
                "Local runbooks",
                "Validated local Markdown sources are available."
                if total
                else "Add a reviewed runbook before starting an analysis.",
                preuve={"count": total},
            )
        ]

    async def vocal(self, langue: str) -> list[dict]:
        resultat = await self.voix.statut(langue)
        pret = resultat.get("pret") is True and resultat.get("local") is True
        return [
            controle(
                "voice_" + langue,
                "voice",
                "pass" if pret else "warn",
                "English voice" if langue == "en" else "French voice",
                "The offline voice runtime verified its model files."
                if pret
                else "The optional offline voice runtime or its models are unavailable.",
                requis=False,
                preuve={"language": langue, "installed": pret},
                commande="./plateforme voix statut --langue " + langue,
            )
        ]

    async def mcp(self, cible: str) -> list[dict]:
        env = {k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "LANG"}}
        env.update(
            PLATFORM_ROOT=str(self.p.racine),
            PLATFORM_STATE_DIR=str(self.p.etat),
            PLATFORM_PORT=str(self.p.port),
            RUNBOOK_DIR=str(self.p.racine / "runbooks"),
        )
        if cible == "control":
            executable, arguments = sys.executable, ["-m", "plateforme.mcp"]
            attendus = {
                "plateforme_preparation",
                "plateforme_outils",
                "plateforme_lire_runbook",
                "plateforme_journal",
                "plateforme_sante",
                "plateforme_analyses",
                "plateforme_analyse",
                "plateforme_runbooks",
                "plateforme_recherche",
            }
        else:
            executable = str(self.p.racine / "mcp-servers/runbooks/.venv/bin/python")
            arguments = [str(self.p.racine / "mcp-servers/runbooks/server.py")]
            attendus = {"list_runbooks", "read_runbook", "search_runbooks", "semantic_search"}
        outils = await inventorier_mcp(executable, arguments, env)
        ok = attendus == outils
        return [
            controle(
                "mcp_" + cible,
                "mcp",
                "pass" if ok else "fail",
                "Control MCP" if cible == "control" else "Runbooks MCP",
                "An actual stdio handshake returned the expected tool inventory."
                if ok
                else "The live tool inventory is incomplete.",
                preuve={"handshake": True, "expected_tools_present": ok, "tool_count": len(outils)},
            )
        ]
