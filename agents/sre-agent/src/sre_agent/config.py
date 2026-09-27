"""Agent configuration: aliases, keys, budgets, tracing.

Two of the CLAUDE.md rules are enforced here, in code, not in a prompt:

- Rule 1: no provider model name. The code knows gateway aliases and
  nothing else. The alias -> model mapping lives in
  ~/platform/workspace/gateway/config.yaml and nowhere else.
- Rule 2: the aliases are partitioned into two disjoint sets, LOCAUX and
  FRONTIERE. That partition is what makes the compartmentalisation guard
  in llm.py decidable.
"""

from __future__ import annotations

import math
import os
from enum import StrEnum
from pathlib import Path


class ConfigurationInvalide(RuntimeError):
    """The configuration cannot start without breaking one of the rules."""


_ERREURS: list[str] = []


def _nombre(nom: str, defaut: float) -> int | float:
    try:
        valeur = type(defaut)(os.environ.get(nom, str(defaut)))
        if not math.isfinite(valeur) or valeur < 0:
            raise ValueError
        return valeur
    except ValueError:
        _ERREURS.append(nom)
        return defaut


# Disable implicit third-party tracing before LangGraph/LangSmith is imported.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

# --- Alias partition ------------------------------------------------------

ALIAS_LOCAUX = frozenset({"local", "local-embed"})
ALIAS_FRONTIERE = frozenset({"smart", "balanced", "fast"})
ALIAS_CONNUS = ALIAS_LOCAUX | ALIAS_FRONTIERE


class Classification(StrEnum):
    """Classification of the data carried by an LLM call.

    CONFIDENTIEL: the payload holds raw alert data, that is, customer
    data. It may only target a local alias.

    DERIVE: reserved for explicitly public or synthetic payloads in separate
    callers. The SRE pipeline never uses it: extraction is not declassification.
    """

    CONFIDENTIEL = "confidentiel"
    DERIVE = "derive"


# --- Roles, expressed as aliases ------------------------------------------

# Alert triage: confidential payload, so a local alias is mandatory.
ALIAS_CLASSIFICATION = "local"
# Alert extraction/anonymisation: same.
ALIAS_EXTRACTION = "local"
# An extraction remains confidential: a model cannot declassify data.
ALIAS_RAISONNEMENT = os.environ.get("SRE_ALIAS_RAISONNEMENT", "local")

# --- Budgets --------------------------------------------------------------

# Tool-call ceiling per alert. Lower it for a demo.
MAX_APPELS_OUTILS = int(_nombre("SRE_MAX_APPELS_OUTILS", 10))
# Monetary ceiling per alert, in USD, computed from the cost the gateway
# reports. Local costs 0, so only the frontier draws on it.
MAX_COUT_USD = float(_nombre("SRE_MAX_COUT_USD", 0.50))

# Loop-turn ceiling. Distinct from the tool budget: a turn may call no
# tool at all. It guards against an endless loop.
MAX_TOURS = int(_nombre("SRE_MAX_TOURS", 12))
MAX_ALERTE = 20_000
MAX_CONTEXTE = 100_000
MAX_DUREE_S = float(_nombre("SRE_MAX_DUREE_S", 1_800.0))

# --- Gateway --------------------------------------------------------------

LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://localhost:4000/v1")
TIMEOUT_LLM_S = float(_nombre("SRE_TIMEOUT_LLM_S", 300.0))

# --- Tracing --------------------------------------------------------------

# Tempo publishes its OTLP/HTTP receiver on 127.0.0.1:4318 (the gateway
# compose stack). NEVER put a container address back here: they are handed
# out in start-up order and change on the first `up`, which points the
# export at another service with no symptom whatsoever: tracing fails
# silently by design. Overridable through OTEL_EXPORTER_OTLP_ENDPOINT.
OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")
SERVICE_NAME = os.environ.get("SRE_SERVICE_NAME", "sre-agent")
TRACAGE_ACTIF = os.environ.get("SRE_TRACAGE", "1") not in {"0", "false", "no"}

# --- Runbooks MCP server --------------------------------------------------

_racine_source = Path(__file__).resolve().parents[4]
RACINE_DEPOT = os.environ.get("SRE_RACINE_DEPOT", str(_racine_source))
MCP_RUNBOOKS_DIR = os.path.join(RACINE_DEPOT, "mcp-servers", "runbooks")
RUNBOOK_DIR = os.environ.get("RUNBOOK_DIR", os.path.join(RACINE_DEPOT, "runbooks"))
QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "runbooks-current")


def valider(alerte: str | None = None) -> None:
    if _ERREURS:
        raise ConfigurationInvalide("Paramètre numérique invalide : " + ", ".join(_ERREURS))
    for valeur in (MAX_COUT_USD, TIMEOUT_LLM_S, MAX_DUREE_S):
        if not math.isfinite(valeur) or valeur <= 0:
            raise ConfigurationInvalide(
                "Plafonds et délais : nombres finis strictement positifs requis."
            )
    if MAX_APPELS_OUTILS < 0 or not 1 <= MAX_TOURS <= 100:
        raise ConfigurationInvalide(
            "Budget d'outils positif ou nul ; tours compris entre 1 et 100."
        )
    if any(a != "local" for a in (ALIAS_EXTRACTION, ALIAS_CLASSIFICATION, ALIAS_RAISONNEMENT)):
        raise ConfigurationInvalide(
            "Le pipeline SRE traite des données confidentielles : alias local requis."
        )
    if alerte is not None and (not alerte.strip() or len(alerte) > MAX_ALERTE):
        raise ConfigurationInvalide(f"L'alerte doit contenir entre 1 et {MAX_ALERTE} caractères.")


def cle(classification: Classification) -> str:
    """Return the virtual key matching the classification.

    A confidential payload uses the key restricted to local aliases. That
    is the second barrier: even if the application-level guard in llm.py
    were bypassed, the gateway would refuse the call with a 403.
    """
    nom = (
        "CONFIDENTIAL_KEY" if classification is Classification.CONFIDENTIEL else "ORCHESTRATOR_KEY"
    )
    valeur = os.environ.get(nom)
    if not valeur:
        raise ConfigurationInvalide(
            f"{nom} absente de l'environnement. "
            "Les clés viennent de .env chargé par direnv : lancer `direnv allow` "
            "à la racine du workspace, ou exporter la variable."
        )
    return valeur
