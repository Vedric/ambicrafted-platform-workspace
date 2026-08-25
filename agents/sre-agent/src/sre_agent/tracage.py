"""Traçage OpenTelemetry vers Tempo.

Une exécution = une span parente `task.incident_analysis`. Chaque appel
LLM et chaque appel d'outil est une span enfant. La trace est le compte
rendu vérifiable de ce que l'agent a fait : quel alias, sur quelle
classification de donnée, pour quel coût.

Le préfixe `ambicrafted.` porte ce que la sémantique gen_ai ne couvre
pas : la classification de la donnée et le type de tâche.

Le traçage ne doit jamais faire échouer l'agent. Si Tempo est
injoignable, l'export échoue en silence dans son thread de fond et
l'analyse se poursuit.
"""

from __future__ import annotations

import atexit
import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from . import config

# Attributs maison. Nommés une seule fois, pour qu'une requête Grafana
# écrite aujourd'hui reste valable demain.
ATTR_CLASSIFICATION = "ambicrafted.data_classification"
ATTR_COUT = "ambicrafted.cost_usd"
ATTR_TYPE_TACHE = "ambicrafted.task.type"
ATTR_ALIAS = "ambicrafted.gateway.alias"
ATTR_OUTIL_SOURCE = "ambicrafted.tool.source"
ATTR_BUDGET_OUTILS = "ambicrafted.budget.tool_calls"
ATTR_BUDGET_MAX_OUTILS = "ambicrafted.budget.max_tool_calls"
ATTR_BUDGET_MAX_COUT = "ambicrafted.budget.max_cost_usd"
ATTR_VERDICT = "ambicrafted.outcome"

_initialise = False


def initialiser() -> None:
    """Installe le fournisseur de spans. Idempotent."""
    global _initialise
    if _initialise:
        return
    _initialise = True

    if not config.TRACAGE_ACTIF:
        return

    # L'exporteur bavarde en warning à chaque échec réseau : en incident
    # c'est du bruit qui masque la sortie utile de l'agent.
    logging.getLogger("opentelemetry.exporter.otlp").setLevel(logging.ERROR)
    logging.getLogger("opentelemetry.sdk.trace.export").setLevel(logging.ERROR)

    fournisseur = TracerProvider(
        resource=Resource.create(
            {
                "service.name": config.SERVICE_NAME,
                "service.version": "0.1.0",
            }
        )
    )
    fournisseur.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=config.OTLP_ENDPOINT.rstrip("/") + "/v1/traces")
        )
    )
    trace.set_tracer_provider(fournisseur)
    # Les spans partent par lots : sans vidage explicite, une exécution
    # courte se termine avant que quoi que ce soit ne soit envoyé.
    atexit.register(vider)


def tracer() -> trace.Tracer:
    initialiser()
    return trace.get_tracer("sre-agent")


def vider(timeout_ms: int = 5_000) -> None:
    """Force l'envoi des spans en attente."""
    fournisseur = trace.get_tracer_provider()
    if isinstance(fournisseur, TracerProvider):
        fournisseur.force_flush(timeout_ms)
