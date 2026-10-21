"""Content-free local OTLP: explicit resources, bounded SDK batching, no request I/O."""

import json
import logging
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from uuid import UUID

import httpx
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanLimits, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from opentelemetry.trace import SpanKind, StatusCode

from . import __version__

OTLP_LOCAL = "http://127.0.0.1:4318/v1/traces"
CAPACITE = 256
journal = logging.getLogger("plateforme.operations")
actuel: ContextVar = ContextVar("plateforme_tracer", default=None)


class ExportLocal(SpanExporter):
    """Official OTLP encoding with an allowlisted transport, no redirects or environment."""

    def __init__(self, mesures, liberer, transport=None):
        self.mesures, self.liberer, self.transport = mesures, liberer, transport

    def export(self, spans):
        accepted = 0
        try:
            payload = encode_spans(spans).SerializeToString()
            with (
                httpx.Client(
                    trust_env=False,
                    follow_redirects=False,
                    timeout=2,
                    transport=self.transport,
                ) as client,
                client.stream(
                    "POST",
                    OTLP_LOCAL,
                    content=payload,
                    headers={
                        "Content-Type": "application/x-protobuf",
                        "Accept-Encoding": "identity",
                    },
                ) as response,
            ):
                response.raise_for_status()
                if (
                    response.status_code != 200
                    or response.headers.get("content-encoding", "identity").lower() != "identity"
                ):
                    raise ValueError("Unsupported telemetry acknowledgement")
                body = bytearray()
                deadline = time.monotonic() + 2
                # Refuse compression before iteration; decompression can allocate before a cap.
                # Inspect each received chunk; rechunking would hide a slowly trickling body.
                for chunk in response.iter_bytes():
                    if len(body) + len(chunk) > 65536 or time.monotonic() > deadline:
                        raise ValueError("Bounded telemetry response")
                    body.extend(chunk)
                result = ExportTraceServiceResponse.FromString(bytes(body))
                rejected = result.partial_success.rejected_spans
                if not 0 <= rejected <= len(spans):
                    raise ValueError("Invalid telemetry acknowledgement")
                accepted = len(spans) - rejected
        except Exception:  # noqa: BLE001 -- optional telemetry must never affect application work
            # Telemetry is optional. Never log exceptions, response bodies or headers.
            accepted = 0
        finally:
            self.mesures.trace_spans.labels("sent").inc(accepted)
            self.mesures.trace_spans.labels("failed").inc(len(spans) - accepted)
            self.liberer(len(spans))
        return SpanExportResult.SUCCESS if accepted == len(spans) else SpanExportResult.FAILURE

    def shutdown(self):
        pass


class LotBorne(SpanProcessor):
    """Admission includes in-flight exports, so SDK queue overflow cannot hide losses."""

    def __init__(self, mesures, transport=None):
        self.mesures, self.attente, self.ferme = mesures, 0, False
        self.verrou = threading.Lock()
        self.batch = BatchSpanProcessor(
            ExportLocal(mesures, self.liberer, transport),
            max_queue_size=CAPACITE + 1,
            max_export_batch_size=32,
            schedule_delay_millis=1000,
            export_timeout_millis=3000,
        )

    def liberer(self, count):
        with self.verrou:
            self.attente -= count

    def on_end(self, span):
        with self.verrou:
            if self.ferme or self.attente >= CAPACITE:
                self.mesures.trace_spans.labels("dropped").inc()
                return
            self.attente += 1
            self.mesures.trace_spans.labels("queued").inc()
            self.batch.on_end(span)

    def shutdown(self):
        with self.verrou:
            self.ferme = True
        self.batch.shutdown()

    def force_flush(self, timeout_millis=30000):
        # Reserved for qualification/shutdown, never invoked by a dialogue route.
        return self.batch.force_flush(timeout_millis)


class Tracage:
    def __init__(self, mesures, *, actif=False, transport=None):
        self.mesures, self.fournisseur, self.handler = mesures, None, None
        mesures.trace_enabled.set(int(actif))
        self.tracer = trace.NoOpTracerProvider().get_tracer("plateforme")
        if actif:
            # Resource.create would import arbitrary OTEL_RESOURCE_ATTRIBUTES from the host.
            self.fournisseur = TracerProvider(
                resource=Resource(
                    {"service.name": "ambicrafted-control", "service.version": __version__}
                ),
                sampler=ALWAYS_ON,
                shutdown_on_exit=False,
                span_limits=SpanLimits(
                    max_attributes=16, max_events=0, max_links=0, max_attribute_length=128
                ),
            )
            self.fournisseur.add_span_processor(LotBorne(mesures, transport))
            self.tracer = self.fournisseur.get_tracer("plateforme")

    def journaliser(self):
        """Uvicorn does not configure arbitrary application loggers; stderr goes to journald."""
        self.handler = logging.StreamHandler()
        self.handler.setFormatter(logging.Formatter("%(message)s"))
        journal.addHandler(self.handler)
        journal.setLevel(logging.INFO)

    def fermer(self):
        if self.fournisseur:
            self.fournisseur.shutdown()
        if self.handler:
            journal.removeHandler(self.handler)
            self.handler.close()


@contextmanager
def etape(nom):
    """Only finite application-owned stage names; no automatic exception events."""
    if nom not in {"document.generate", "document.review", "document.store", "aura.gateway"}:
        raise ValueError("Unknown telemetry stage")
    tracer = actuel.get()
    if tracer is None:
        yield
        return
    with tracer.start_as_current_span(
        nom,
        kind=SpanKind.CLIENT if nom == "aura.gateway" else SpanKind.INTERNAL,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            yield
        except BaseException:
            span.set_status(StatusCode.ERROR)
            raise


def entetes_trace():
    """No incoming baggage/tracestate propagation; only our locally created trace context."""
    span = trace.get_current_span().get_span_context()
    if actuel.get() is None or not span.is_valid:
        return {}
    return {
        "traceparent": f"00-{span.trace_id:032x}-{span.span_id:016x}-{int(span.trace_flags):02x}"
    }


def tracer_flux(function):
    """Keep one client span across a stream without ContextVar tokens crossing yields."""

    @wraps(function)
    async def flux(*args, **kwargs):
        tracer = actuel.get()
        span = tracer.start_span("aura.gateway", kind=SpanKind.CLIENT) if tracer else None
        source = function(*args, **kwargs)
        try:
            while True:
                if span:
                    with trace.use_span(
                        span, record_exception=False, set_status_on_exception=False
                    ):
                        event = await anext(source, None)
                else:
                    event = await anext(source, None)
                if event is None:
                    break
                yield event
        except BaseException:
            if span:
                span.set_status(StatusCode.ERROR)
            raise
        finally:
            try:
                await source.aclose()
            finally:
                if span:
                    span.end()

    return flux


class Operation:
    """One admitted attempt, exactly one terminal, independent of HTTP status and retries."""

    def __init__(self, tracage, format, *, vocal=False, operation_id=None):
        if format not in {"text", "diagram", "report"}:
            raise ValueError("Unknown operation format")
        if operation_id is not None:
            operation_id = str(UUID(operation_id))
        self.tracage, self.format, self.vocal = tracage, format, vocal
        self.operation_id, self.debut, self.fini, self.premier = (
            operation_id,
            time.monotonic(),
            False,
            False,
        )
        self.span = tracage.tracer.start_span(
            "aura.operation",
            context=Context(),
            kind=SpanKind.SERVER,
            attributes={
                "ambicrafted.format": format,
                "ambicrafted.mode": "voice" if vocal else "text",
            },
        )

    @property
    def trace_id(self):
        context = self.span.get_span_context()
        return f"{context.trace_id:032x}" if context.is_valid else None

    @contextmanager
    def activer(self):
        token = actuel.set(self.tracage.tracer)
        try:
            with trace.use_span(self.span, record_exception=False, set_status_on_exception=False):
                yield
        finally:
            actuel.reset(token)

    def token(self):
        if not self.premier:
            self.premier = True
            self.tracage.mesures.first_token.labels("voice" if self.vocal else "text").observe(
                time.monotonic() - self.debut
            )

    def terminer(self, outcome):
        if outcome not in {"success", "error", "timeout", "cancelled"}:
            raise ValueError("Unknown telemetry outcome")
        if self.fini:
            return
        self.fini = True
        self.tracage.mesures.aura.labels(self.format, outcome).inc()
        self.tracage.mesures.aura_duration.labels(self.format, outcome).observe(
            time.monotonic() - self.debut
        )
        self.span.set_attribute("ambicrafted.outcome", outcome)
        self.span.set_status(StatusCode.OK if outcome == "success" else StatusCode.ERROR)
        self.span.end()
        event = {"event": "aura.operation.finished", "format": self.format, "outcome": outcome}
        if self.operation_id:
            event["operation_id"] = self.operation_id
        if self.trace_id:
            event["trace_id"] = self.trace_id
        journal.info(json.dumps(event))
