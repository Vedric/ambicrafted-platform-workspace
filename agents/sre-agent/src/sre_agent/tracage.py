"""OpenTelemetry tracing to Tempo.

One run = one parent span `task.incident_analysis`. Every LLM call and
every tool call is a child span. The trace is the verifiable account of
what the agent did: which alias, on which data classification, at what
cost.

The `ambicrafted.` prefix carries what the gen_ai semantics leave out:
the data classification and the task type.

Tracing must never bring the agent down. If Tempo is unreachable the
export fails silently in its background thread and the analysis carries
on.
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

# House attributes. Named once, so that a Grafana query written today
# still resolves tomorrow.
ATTR_CLASSIFICATION = "ambicrafted.data_classification"
ATTR_COUT = "ambicrafted.cost_usd"
ATTR_COUT_TOTAL = "ambicrafted.run.cost_usd"
ATTR_TYPE_TACHE = "ambicrafted.task.type"
ATTR_ALIAS = "ambicrafted.gateway.alias"
ATTR_OUTIL_SOURCE = "ambicrafted.tool.source"
ATTR_BUDGET_OUTILS = "ambicrafted.budget.tool_calls"
ATTR_BUDGET_MAX_OUTILS = "ambicrafted.budget.max_tool_calls"
ATTR_BUDGET_MAX_COUT = "ambicrafted.budget.max_cost_usd"
ATTR_VERDICT = "ambicrafted.outcome"

_initialise = False


def initialiser() -> None:
    """Install the span provider. Idempotent."""
    global _initialise
    if _initialise:
        return
    _initialise = True

    if not config.TRACAGE_ACTIF:
        return

    # The exporter warns on every network failure: during an incident that
    # is noise, and it buries the agent's useful output.
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
    # Spans leave in batches: without an explicit flush, a short run ends
    # before anything has been sent.
    atexit.register(vider)


def tracer() -> trace.Tracer:
    initialiser()
    return trace.get_tracer("sre-agent")


def vider(timeout_ms: int = 5_000) -> None:
    """Force the pending spans out."""
    fournisseur = trace.get_tracer_provider()
    if isinstance(fournisseur, TracerProvider):
        fournisseur.force_flush(timeout_ms)
