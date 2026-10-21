"""Prove local-only protobuf transport, propagation, bounded losses and no content leakage."""

import asyncio
import json
import logging
import threading
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from starlette.requests import ClientDisconnect

from plateforme.conversation_routes import ReponseDialogue
from plateforme.observabilite import Mesures
from plateforme.tracage import (
    CAPACITE,
    ExportLocal,
    LotBorne,
    Operation,
    Tracage,
    entetes_trace,
    etape,
)


def provider():
    measures = Mesures()
    capture = InMemorySpanExporter()
    tracing = Tracage(measures)
    tracing.fournisseur = TracerProvider(shutdown_on_exit=False)
    tracing.fournisseur.add_span_processor(SimpleSpanProcessor(capture))
    tracing.tracer = tracing.fournisseur.get_tracer("test")
    return measures, tracing, capture


def test_explicit_trace_context_no_error_content_or_client_context(caplog):
    measures, tracing, capture = provider()
    operation = Operation(tracing, "report", operation_id=str(uuid4()))
    with caplog.at_level(logging.INFO, logger="plateforme.operations"):
        with operation.activer():
            assert entetes_trace()["traceparent"].split("-")[1] == operation.trace_id
            with pytest.raises(ValueError), etape("document.generate"):
                raise ValueError("private prompt and upstream credential")
        assert entetes_trace() == {}
        operation.terminer("error")
        operation.terminer("success")
    spans = capture.get_finished_spans()
    assert len(spans) == 2 and spans[0].parent.span_id == spans[1].context.span_id
    assert spans[1].parent is None
    assert all(not span.events and not span.status.description for span in spans)
    assert "private prompt" not in caplog.text
    assert json.loads(caplog.records[-1].message)["trace_id"] == operation.trace_id
    assert measures.aura.labels("report", "error")._value.get() == 1
    assert measures.aura.labels("report", "success")._value.get() == 0
    tracing.fermer()


def test_non_uuid_operation_id_cannot_enter_log():
    with pytest.raises(ValueError):
        Operation(Tracage(Mesures()), "text", operation_id="customer-secret")


@pytest.mark.parametrize(
    "behavior",
    [
        "ok",
        "partial",
        "redirect",
        "malformed",
        "oversize",
        "error",
        "not_otlp_success",
        "compressed",
        "negative_rejected",
        "excess_rejected",
    ],
)
def test_actual_encoder_fixed_endpoint_no_env_or_response_body_leak(monkeypatch, caplog, behavior):
    for key in (
        "OTEL_RESOURCE_ATTRIBUTES",
        "OTEL_EXPORTER_OTLP_HEADERS",
        "OTEL_EXPORTER_OTLP_TRACES_HEADERS",
    ):
        monkeypatch.setenv(key, "private-canary=private-value")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "https://external.invalid/private")
    monkeypatch.setenv("HTTP_PROXY", "http://external.invalid:1234")
    requests = []

    def receive(request):
        requests.append(request)
        assert str(request.url) == "http://127.0.0.1:4318/v1/traces"
        assert "private" not in str(request.headers)
        assert request.headers["accept-encoding"] == "identity"
        decoded = ExportTraceServiceRequest.FromString(request.content)
        assert "private" not in str(decoded)
        assert (
            decoded.resource_spans[0].resource.attributes[0].value.string_value
            == "ambicrafted-control"
        )
        if behavior == "error":
            raise httpx.ConnectError("private upstream error", request=request)
        if behavior == "redirect":
            return httpx.Response(302, headers={"Location": "https://external.invalid/private"})
        if behavior == "malformed":
            return httpx.Response(200, content=b"private invalid protobuf")
        if behavior == "oversize":
            return httpx.Response(200, content=b"x" * 65537)
        if behavior == "not_otlp_success":
            return httpx.Response(204)
        if behavior == "compressed":

            class Unread(httpx.SyncByteStream):
                def __iter__(self):
                    pytest.fail("Compressed responses must be refused before decoding or reading")
                    yield b"unreachable"

            return httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=Unread())
        response = ExportTraceServiceResponse()
        if behavior == "partial":
            response.partial_success.rejected_spans = 1
            response.partial_success.error_message = "private collector detail"
        if behavior in {"negative_rejected", "excess_rejected"}:
            response.partial_success.rejected_spans = -1 if behavior == "negative_rejected" else 2
        return httpx.Response(200, content=response.SerializeToString())

    measures = Mesures()
    tracing = Tracage(measures, actif=True, transport=httpx.MockTransport(receive))
    operation = Operation(tracing, "text")
    operation.terminer("success")
    tracing.fermer()
    assert len(requests) == 1
    assert measures.trace_spans.labels("queued")._value.get() == 1
    assert measures.trace_spans.labels("sent")._value.get() == int(behavior == "ok")
    assert measures.trace_spans.labels("failed")._value.get() == int(behavior != "ok")
    assert "private" not in caplog.text


def test_blocked_export_never_blocks_requests_and_exact_overflow_is_counted():
    entered, release = threading.Event(), threading.Event()

    def blocked(request):
        entered.set()
        assert release.wait(5)
        return httpx.Response(200)

    measures = Mesures()
    processor = LotBorne(measures, httpx.MockTransport(blocked))
    tracing = TracerProvider(shutdown_on_exit=False)
    tracing.add_span_processor(processor)
    tracer = tracing.get_tracer("test")
    try:
        for _ in range(32):
            tracer.start_span("safe").end()
        assert entered.wait(2)
        for _ in range(CAPACITE):
            tracer.start_span("safe").end()
        assert measures.trace_spans.labels("queued")._value.get() == CAPACITE
        assert measures.trace_spans.labels("dropped")._value.get() == 32
        assert processor.attente == CAPACITE
    finally:
        release.set()
        tracing.shutdown()
    assert measures.trace_spans.labels("sent")._value.get() == CAPACITE
    assert processor.attente == 0


def test_trickling_response_checks_deadline_without_waiting_for_a_full_chunk(monkeypatch):
    clock = [0.0]
    consumed = []
    released = []
    measures, tracing, capture = provider()
    Operation(tracing, "text").terminer("success")

    class Trickle(httpx.SyncByteStream):
        def __iter__(self):
            for index in range(10):
                clock[0] += 1.0
                consumed.append(index)
                yield b"x"

    monkeypatch.setattr("plateforme.tracage.time.monotonic", lambda: clock[0])
    exporter = ExportLocal(
        measures,
        released.append,
        httpx.MockTransport(lambda _: httpx.Response(200, stream=Trickle())),
    )
    exporter.export(capture.get_finished_spans())
    assert consumed == [0, 1, 2]
    assert released == [1]
    assert measures.trace_spans.labels("failed")._value.get() == 1
    assert measures.trace_spans.labels("sent")._value.get() == 0
    tracing.fermer()


@pytest.mark.asyncio
async def test_header_failure_before_generator_start_counts_cancellation_once():
    measures = Mesures()
    operation = Operation(Tracage(measures), "text")
    lock = asyncio.Lock()
    await lock.acquire()

    async def events():
        pytest.fail("Generator must not start before headers")
        yield "unreachable"

    async def fail_send(_):
        raise OSError("private socket error")

    response = ReponseDialogue(events(), lock, operation)
    with pytest.raises(ClientDisconnect):
        await response({"type": "http", "asgi": {"spec_version": "2.4"}}, None, fail_send)
    assert not lock.locked()
    assert measures.aura.labels("text", "cancelled")._value.get() == 1


@pytest.mark.parametrize("stage", ["startup", "shutdown"])
def test_application_closes_export_worker_even_when_component_lifecycle_fails(
    application, parametres, monkeypatch, stage
):
    closed = threading.Event()
    monkeypatch.setattr(application.state.tracage, "fermer", closed.set)

    async def fail():
        raise RuntimeError("Synthetic lifecycle failure")

    monkeypatch.setattr(
        application.state.moteur if stage == "startup" else application.state.voix,
        "demarrer" if stage == "startup" else "fermer",
        fail,
    )
    with (
        pytest.raises(RuntimeError, match="Synthetic lifecycle failure"),
        TestClient(application, base_url=parametres.url),
    ):
        pass
    assert closed.is_set()
