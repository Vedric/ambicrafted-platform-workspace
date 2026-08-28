"""Configuration de l'agent : alias, clés, budgets, traçage.

Deux règles du CLAUDE.md sont matérialisées ici, pas dans un prompt :

- Règle 1 : aucun nom de modèle fournisseur. Le code ne connaît que des
  alias de passerelle. La correspondance alias -> modèle vit dans
  ~/platform/workspace/gateway/config.yaml et nulle part ailleurs.
- Règle 2 : les alias sont partitionnés en deux ensembles disjoints,
  LOCAUX et FRONTIERE. Cette partition est ce qui rend la garde de
  cloisonnement de llm.py décidable.
"""

from __future__ import annotations

import os
from enum import StrEnum

# --- Partition des alias --------------------------------------------------

ALIAS_LOCAUX = frozenset({"local", "local-embed"})
ALIAS_FRONTIERE = frozenset({"smart", "balanced", "fast"})
ALIAS_CONNUS = ALIAS_LOCAUX | ALIAS_FRONTIERE


class Classification(StrEnum):
    """Classification de la donnée transportée par un appel LLM.

    CONFIDENTIEL : la charge contient de la donnée d'alerte brute, c'est
    à dire de la donnée client. Elle ne peut viser qu'un alias local.

    DERIVE : la charge ne contient que des éléments déjà extraits et
    anonymisés par une étape locale, plus du contenu de runbook, qui est
    notre propre documentation. La frontière est autorisée.
    """

    CONFIDENTIEL = "confidentiel"
    DERIVE = "derive"


# --- Rôles, exprimés en alias ---------------------------------------------

# Classification de l'alerte : charge confidentielle, donc local imposé.
ALIAS_CLASSIFICATION = "local"
# Extraction/anonymisation de l'alerte : idem.
ALIAS_EXTRACTION = "local"
# Raisonnement final sur données dérivées : frontière autorisée.
ALIAS_RAISONNEMENT = os.environ.get("SRE_ALIAS_RAISONNEMENT", "smart")

# --- Budgets --------------------------------------------------------------

# Plafond d'appels d'outils par alerte. Abaissable pour la démonstration.
MAX_APPELS_OUTILS = int(os.environ.get("SRE_MAX_APPELS_OUTILS", "10"))
# Plafond monétaire par alerte, en USD, calculé sur le coût rapporté par
# la passerelle. Le local coûte 0, donc seule la frontière consomme.
MAX_COUT_USD = float(os.environ.get("SRE_MAX_COUT_USD", "0.50"))

# Plafond de tours de boucle. Distinct du budget d'outils : un tour peut
# n'appeler aucun outil. Sert de garde-fou contre une boucle sans fin.
MAX_TOURS = int(os.environ.get("SRE_MAX_TOURS", "12"))

# --- Passerelle -----------------------------------------------------------

LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://localhost:4000/v1")
TIMEOUT_LLM_S = float(os.environ.get("SRE_TIMEOUT_LLM_S", "300"))

# --- Traçage --------------------------------------------------------------

# Tempo publie son récepteur OTLP/HTTP sur 127.0.0.1:4318 (compose de la
# passerelle). Ne JAMAIS remettre une adresse de conteneur ici : elles sont
# attribuées dans l'ordre de démarrage et changent au premier `up`, ce qui
# fait pointer l'export vers un autre service sans le moindre symptôme —
# le traçage échoue en silence par conception. Surchargeable par
# OTEL_EXPORTER_OTLP_ENDPOINT.
OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")
SERVICE_NAME = os.environ.get("SRE_SERVICE_NAME", "sre-agent")
TRACAGE_ACTIF = os.environ.get("SRE_TRACAGE", "1") not in {"0", "false", "no"}

# --- Serveur MCP runbooks -------------------------------------------------

RACINE_DEPOT = os.environ.get(
    "SRE_RACINE_DEPOT", os.path.expanduser("~/platform/workspace")
)
MCP_RUNBOOKS_DIR = os.path.join(RACINE_DEPOT, "mcp-servers", "runbooks")
RUNBOOK_DIR = os.environ.get("RUNBOOK_DIR", os.path.join(RACINE_DEPOT, "runbooks"))
QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")


class ConfigurationInvalide(RuntimeError):
    """La configuration ne permet pas de démarrer sans violer une règle."""


def cle(classification: Classification) -> str:
    """Retourne la clé virtuelle correspondant à la classification.

    Une charge confidentielle utilise la clé restreinte aux alias locaux.
    C'est la seconde barrière : même si la garde applicative de llm.py
    était contournée, la passerelle refuserait l'appel en 403.
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
