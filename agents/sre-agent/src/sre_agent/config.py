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

import os
from enum import StrEnum

# --- Alias partition ------------------------------------------------------

ALIAS_LOCAUX = frozenset({"local", "local-embed"})
ALIAS_FRONTIERE = frozenset({"smart", "balanced", "fast"})
ALIAS_CONNUS = ALIAS_LOCAUX | ALIAS_FRONTIERE


class Classification(StrEnum):
    """Classification of the data carried by an LLM call.

    CONFIDENTIEL: the payload holds raw alert data, that is, customer
    data. It may only target a local alias.

    DERIVE: the payload holds only material already extracted and
    anonymised by a local step, plus runbook content, which is our own
    documentation. The frontier is allowed.
    """

    CONFIDENTIEL = "confidentiel"
    DERIVE = "derive"


# --- Roles, expressed as aliases ------------------------------------------

# Alert triage: confidential payload, so a local alias is mandatory.
ALIAS_CLASSIFICATION = "local"
# Alert extraction/anonymisation: same.
ALIAS_EXTRACTION = "local"
# Final reasoning over derived data: the frontier is allowed.
ALIAS_RAISONNEMENT = os.environ.get("SRE_ALIAS_RAISONNEMENT", "smart")

# --- Budgets --------------------------------------------------------------

# Tool-call ceiling per alert. Lower it for a demo.
MAX_APPELS_OUTILS = int(os.environ.get("SRE_MAX_APPELS_OUTILS", "10"))
# Monetary ceiling per alert, in USD, computed from the cost the gateway
# reports. Local costs 0, so only the frontier draws on it.
MAX_COUT_USD = float(os.environ.get("SRE_MAX_COUT_USD", "0.50"))

# Loop-turn ceiling. Distinct from the tool budget: a turn may call no
# tool at all. It guards against an endless loop.
MAX_TOURS = int(os.environ.get("SRE_MAX_TOURS", "12"))

# --- Gateway --------------------------------------------------------------

LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://localhost:4000/v1")
TIMEOUT_LLM_S = float(os.environ.get("SRE_TIMEOUT_LLM_S", "300"))

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

RACINE_DEPOT = os.environ.get(
    "SRE_RACINE_DEPOT", os.path.expanduser("~/platform/workspace")
)
MCP_RUNBOOKS_DIR = os.path.join(RACINE_DEPOT, "mcp-servers", "runbooks")
RUNBOOK_DIR = os.environ.get("RUNBOOK_DIR", os.path.join(RACINE_DEPOT, "runbooks"))
QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")


class ConfigurationInvalide(RuntimeError):
    """The configuration cannot start without breaking one of the rules."""


def cle(classification: Classification) -> str:
    """Return the virtual key matching the classification.

    A confidential payload uses the key restricted to local aliases. That
    is the second barrier: even if the application-level guard in llm.py
    were bypassed, the gateway would refuse the call with a 403.
    """
    nom = "CONFIDENTIAL_KEY" if classification is Classification.CONFIDENTIEL else "ORCHESTRATOR_KEY"
    valeur = os.environ.get(nom)
    if not valeur:
        raise ConfigurationInvalide(
            f"{nom} absente de l'environnement. "
            "Les clés viennent de .env chargé par direnv : lancer `direnv allow` "
            "à la racine du workspace, ou exporter la variable."
        )
    return valeur
