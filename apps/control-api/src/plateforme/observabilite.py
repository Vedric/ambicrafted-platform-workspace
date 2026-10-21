"""Low-cardinality, content-free metrics for the authenticated local control plane."""

import asyncio
import time
from collections import Counter as Comptes

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    ProcessCollector,
    generate_latest,
)
from prometheus_client.core import GaugeMetricFamily

GROUPS = (
    "auth",
    "analyses",
    "conversations",
    "speech_recognition",
    "speech_synthesis",
    "assistant",
    "memory",
    "knowledge",
    "health",
    "telemetry",
    "other",
)
STATES = (
    "en_file",
    "en_cours",
    "decision",
    "en_attente_humain",
    "complet",
    "rejete_par_humain",
    "erreur",
    "budget_epuise",
    "annule",
    "interrompu",
)
SERVICES = ("litellm", "ollama", "qdrant", "prometheus", "tempo", "grafana")
BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 60, 120, 300)


def group(path: str) -> str:
    """Never export paths, IDs, queries, customer names or source text as labels."""
    if path.startswith("/api/auth"):
        return "auth"
    if path.startswith("/api/telemetrie/"):
        return "telemetry"
    if path.startswith("/api/conversations/") and path.endswith("/messages"):
        return "assistant"
    if path.startswith("/api/voix/transcrire"):
        return "speech_recognition"
    if path.startswith("/api/voix/parler"):
        return "speech_synthesis"
    for prefix, name in (
        ("/api/analyses", "analyses"),
        ("/api/conversations", "conversations"),
        ("/api/assistant", "assistant"),
        ("/api/memoire", "memory"),
        ("/api/runbooks", "knowledge"),
        ("/api/recherche", "knowledge"),
        ("/api/ping", "health"),
        ("/api/sante", "health"),
        ("/api/preparation", "health"),
    ):
        if path.startswith(prefix):
            return name
    return "other"


class Mesures:
    def __init__(self):
        self.registry = CollectorRegistry()
        ProcessCollector(registry=self.registry)
        self.requests = Counter(
            "ambicrafted_http_requests_total",
            "Finished API requests since process start.",
            ["group", "outcome"],
            registry=self.registry,
        )
        self.duration = Histogram(
            "ambicrafted_http_request_duration_seconds",
            "API duration through final response body, including streaming; excludes capture.",
            ["group"],
            buckets=BUCKETS,
            registry=self.registry,
        )
        self.active = Gauge(
            "ambicrafted_http_in_flight",
            "API requests currently executing.",
            ["group"],
            registry=self.registry,
        )
        self.denied = Counter(
            "ambicrafted_auth_rejections_total",
            "API responses with status 401 or 403.",
            registry=self.registry,
        )
        self.aura = Counter(
            "ambicrafted_aura_operations_total",
            "Admitted AURA attempts ending technically; never a correctness measurement.",
            ["format", "outcome"],
            registry=self.registry,
        )
        self.aura_duration = Histogram(
            "ambicrafted_aura_operation_duration_seconds",
            "Admitted AURA work through terminal delivery; cancellations separate.",
            ["format", "outcome"],
            buckets=BUCKETS,
            registry=self.registry,
        )
        self.first_token = Histogram(
            "ambicrafted_aura_first_token_seconds",
            "Time from admission to first nonempty streamed text, excluding capture/playback.",
            ["mode"],
            buckets=BUCKETS,
            registry=self.registry,
        )
        self.replayed = Counter(
            "ambicrafted_aura_replays_total",
            "Completed idempotent replies reused, not new work.",
            registry=self.registry,
        )
        self.admission = Counter(
            "ambicrafted_aura_admission_rejections_total",
            "Requests rejected before inference admission, separate from delivery SLI.",
            ["reason"],
            registry=self.registry,
        )
        self.document_failures = Counter(
            "ambicrafted_document_failures_total",
            "Finite observed document failure categories.",
            ["code"],
            registry=self.registry,
        )
        self.trace_spans = Counter(
            "ambicrafted_trace_spans_total",
            "API spans queued, accepted by local OTLP, failed or dropped; not trace durability.",
            ["outcome"],
            registry=self.registry,
        )
        self.trace_enabled = Gauge(
            "ambicrafted_trace_enabled",
            "Local API trace export enabled; not collector health.",
            registry=self.registry,
        )
        self.web_vitals = Histogram(
            "ambicrafted_browser_web_vital_seconds",
            "Client-reported whole-document LCP/INP, initial authenticated route; not soft navigation.",
            ["metric", "route"],
            buckets=(0.05, 0.1, 0.2, 0.5, 1, 2, 2.5, 4, 8, 15, 30, 60, 300),
            registry=self.registry,
        )
        self.layout_shift = Histogram(
            "ambicrafted_browser_layout_shift_ratio",
            "Client-reported whole-document CLS; missing measurements remain unknown.",
            ["route"],
            buckets=(0, 0.01, 0.05, 0.1, 0.15, 0.25, 0.5, 1, 5, 100),
            registry=self.registry,
        )
        for format in ("text", "diagram", "report"):
            for outcome in ("success", "error", "timeout", "cancelled"):
                self.aura.labels(format, outcome)
                self.aura_duration.labels(format, outcome)
        for outcome in ("queued", "sent", "failed", "dropped"):
            self.trace_spans.labels(outcome)
        for reason in ("busy", "rate_limit"):
            self.admission.labels(reason)
        for name in GROUPS:
            self.active.labels(name).set(0)
            self.duration.labels(name)
            for outcome in ("success", "client_error", "server_error", "cancelled"):
                self.requests.labels(name, outcome)


class MesuresHTTP:
    """ASGI-native wrapper: streaming and cancellation are measured, bodies never read."""

    def __init__(self, app, mesures: Mesures):
        self.app, self.mesures = app, mesures

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] != "http" or not path.startswith("/api/") or path == "/api/metriques":
            return await self.app(scope, receive, send)
        name, start = group(path), time.monotonic()
        status, completed = 500, False
        self.mesures.active.labels(name).inc()

        async def observed(message):
            nonlocal status, completed
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                completed = True

        try:
            await self.app(scope, receive, observed)
        except asyncio.CancelledError:
            status = 499
            raise
        finally:
            outcome = (
                "success" if status < 400 else "client_error" if status < 500 else "server_error"
            )
            if not completed and status < 500:
                outcome = "cancelled"
            self.mesures.requests.labels(name, outcome).inc()
            self.mesures.duration.labels(name).observe(time.monotonic() - start)
            self.mesures.active.labels(name).dec()
            if status in {401, 403}:
                self.mesures.denied.inc()


class Instantane:
    """Retained-store aggregates are gauges: deletion and retention can reduce them."""

    def __init__(self, depot, moteur, health):
        self.depot, self.moteur, self.health = depot, moteur, health

    def collect(self):
        runs = GaugeMetricFamily(
            "ambicrafted_retained_runs",
            "Currently retained runs, not cumulative executions.",
            labels=["kind", "state"],
        )
        with self.depot.connexion() as db:
            rows = db.execute(
                "SELECT mode,statut,count(*) FROM analyses GROUP BY mode,statut"
            ).fetchall()
            counts: Comptes[tuple[str, str]] = Comptes()
            for kind, state, count in rows:
                counts[
                    (
                        kind if kind in ("graphe", "operation") else "other",
                        state if state in STATES else "other",
                    )
                ] += count
            for kind in ("graphe", "operation", "other"):
                for state in (*STATES, "other"):
                    runs.add_metric([kind, state], counts.get((kind, state), 0))
            yield runs
            # Select numeric budget aggregates only; never export a report or a title.
            for field in ("tokens_entree", "tokens_sortie", "tokens_total", "cout_usd"):
                expr = "json_extract(rapport, '$.budget." + field + "')"
                valid = "json_type(rapport, '$.budget." + field + "') IN ('integer','real')"
                value, measured = db.execute(
                    f"SELECT coalesce(sum(CASE WHEN {valid} AND {expr}>=0 THEN {expr} END),0),"
                    f"count(CASE WHEN {valid} AND {expr}>=0 THEN 1 END) "
                    "FROM analyses WHERE mode='graphe'"
                ).fetchone()
                metric = "tokens" if field == "tokens_total" else field
                yield GaugeMetricFamily(
                    "ambicrafted_retained_" + metric,
                    "Observed sum in retained SRE reports; partial when measurements are absent.",
                    value=value,
                )
                yield GaugeMetricFamily(
                    "ambicrafted_retained_" + metric + "_measured_runs",
                    "Retained SRE reports with a valid measurement (zero is measured).",
                    value=measured,
                )
            for table, name in (
                ("conversations", "conversations"),
                ("messages_conversation", "messages"),
                ("pieces_conversation", "documents"),
            ):
                value = db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                yield GaugeMetricFamily(
                    "ambicrafted_retained_" + name, "Retained item count.", value=value
                )
        yield GaugeMetricFamily(
            "ambicrafted_queue_depth",
            "Waiting execution queue entries.",
            value=self.moteur.file.qsize(),
        )
        yield GaugeMetricFamily(
            "ambicrafted_queue_capacity",
            "Configured waiting queue capacity.",
            value=self.moteur.file.maxsize,
        )
        yield GaugeMetricFamily(
            "ambicrafted_inference_busy",
            "Shared inference lease held.",
            value=int(self.moteur.inference.locked()),
        )
        up = GaugeMetricFamily(
            "ambicrafted_service_up", "Fixed local HTTP health probe result.", labels=["service"]
        )
        latency = GaugeMetricFamily(
            "ambicrafted_service_probe_duration_seconds",
            "Last cached health probe duration, not inference latency.",
            labels=["service"],
        )
        for item in self.health.get("services", []):
            if item.get("id") in SERVICES:
                up.add_metric([item["id"]], int(item["ok"]))
                latency.add_metric([item["id"]], item["latence_ms"] / 1000)
        yield up
        yield latency
        points = self.health.get("index", {}).get("points")
        if isinstance(points, int) and points >= 0:
            yield GaugeMetricFamily(
                "ambicrafted_index_points", "Published runbook index points.", value=points
            )


def exposer(mesures, depot, moteur, health) -> bytes:
    registry = CollectorRegistry()
    registry.register(Instantane(depot, moteur, health))
    return generate_latest(mesures.registry) + generate_latest(registry)
