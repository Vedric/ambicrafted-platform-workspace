"""Business terminals must not inherit misleading HTTP200 success or count replay twice."""

import asyncio
import json
import uuid

import httpx
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from starlette.requests import ClientDisconnect

from plateforme.conversations import Conversations
from plateforme.erreurs_document import CodeErreurDocument, ErreurDocument


def request_turn(client, bearer, **changes):
    identifier = client.post("/api/conversations", headers=bearer, json={}).json()["id"]
    charge = {"message": "Synthetic request", "operation_id": str(uuid.uuid4()), **changes}
    return f"/api/conversations/{identifier}/messages", charge


def test_success_replay_and_first_token_have_distinct_accounting(
    client, bearer, application, monkeypatch
):
    async def generate(*args, **kwargs):
        yield {"type": "token", "text": "Synthetic"}
        yield {"type": "token", "text": " answer"}
        yield {"type": "done", "texte": "Synthetic answer", "usage": {}, "local": True}

    monkeypatch.setattr("plateforme.conversation_routes.flux_dialogue", generate)
    url, charge = request_turn(client, bearer)
    for _ in range(2):
        assert client.post(url, headers=bearer, json=charge).status_code == 200
    measures = application.state.mesures
    assert measures.aura.labels("text", "success")._value.get() == 1
    assert measures.aura.labels("text", "cancelled")._value.get() == 0
    assert measures.replayed._value.get() == 1
    samples = measures.first_token.collect()[0].samples
    assert next(sample.value for sample in samples if sample.name.endswith("_count")) == 1


@pytest.mark.parametrize(
    "error,outcome,code",
    [
        (ValueError("private upstream"), "error", "document_unknown"),
        (httpx.ReadTimeout("private upstream"), "timeout", "document_timeout"),
        (ErreurDocument(CodeErreurDocument.REVUE_REFUSEE), "error", "document_review_rejected"),
    ],
)
def test_http200_error_is_bad_business_terminal_without_partial_save(
    client, bearer, application, monkeypatch, error, outcome, code
):
    async def generate(*args):
        raise error

    monkeypatch.setattr("plateforme.conversation_routes.generer_artefact", generate)
    url, charge = request_turn(client, bearer, format="report")
    response = client.post(url, headers=bearer, json=charge)
    assert response.status_code == 200
    assert json.loads(response.text)["code"] == code
    assert "private upstream" not in response.text
    measures = application.state.mesures
    assert measures.requests.labels("assistant", "success")._value.get() == 1
    assert measures.aura.labels("report", outcome)._value.get() == 1
    assert measures.aura.labels("report", "success")._value.get() == 0
    assert measures.document_failures.labels(code)._value.get() == 1
    assert client.get(url.removesuffix("/messages"), headers=bearer).json()["total_messages"] == 0


def test_busy_is_admission_not_delivery_failure(client, bearer, application):
    url, charge = request_turn(client, bearer)
    application.state.moteur.file.put_nowait("synthetic")
    assert client.post(url, headers=bearer, json=charge).status_code == 409
    measures = application.state.mesures
    assert measures.admission.labels("busy")._value.get() == 1
    assert (
        sum(
            sample.value
            for sample in measures.aura.collect()[0].samples
            if sample.name.endswith("_total")
        )
        == 0
    )


def test_real_stream_propagates_only_local_child_trace_and_never_content(
    client,
    bearer,
    application,
    monkeypatch,
    caplog,
):
    requests = []
    capture = InMemorySpanExporter()
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(SimpleSpanProcessor(capture))
    application.state.tracage.tracer = provider.get_tracer("synthetic-api")
    actual = httpx.AsyncClient

    def receive(request):
        requests.append(request)
        return httpx.Response(
            200,
            content=(
                b'data: {"choices":[{"delta":{"content":"SYNTHETIC_PRIVATE_OUTPUT"}}]}\n\n'
                b"data: [DONE]\n\n"
            ),
        )

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: actual(transport=httpx.MockTransport(receive), **kw)
    )
    url, charge = request_turn(client, bearer, message="SYNTHETIC_PRIVATE_INPUT")
    response = client.post(
        url,
        headers={
            **bearer,
            "traceparent": "00-" + "a" * 32 + "-" + "b" * 16 + "-01",
            "baggage": "customer=SYNTHETIC_PRIVATE_METADATA",
        },
        json=charge,
    )
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines()]
    trace_id = events[-1]["trace_id"]
    assert trace_id != "a" * 32 and all(event["trace_id"] == trace_id for event in events)
    assert len(requests) == 1 and "baggage" not in requests[0].headers
    spans = capture.get_finished_spans()
    root = next(span for span in spans if span.name == "aura.operation")
    gateway = next(span for span in spans if span.name == "aura.gateway")
    assert root.parent is None and gateway.parent.span_id == root.context.span_id
    assert requests[0].headers["traceparent"].split("-")[2] == f"{gateway.context.span_id:016x}"
    assert f"{root.context.trace_id:032x}" == trace_id
    assert all(
        "SYNTHETIC_PRIVATE" not in str(span.attributes) + str(span.events) + str(span.status)
        for span in spans
    )
    assert "SYNTHETIC_PRIVATE" not in caplog.text
    provider.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_event", ["token", "done"])
async def test_failed_asgi_delivery_is_cancelled_and_closes_upstream(
    application, parametres, bearer, monkeypatch, failed_event
):
    """A generated or persisted answer is not a delivered answer when ASGI send rejects it."""
    closed = False

    async def generate(*args, **kwargs):
        nonlocal closed
        try:
            yield {"type": "token", "text": "Synthetic"}
            yield {"type": "done", "texte": "Synthetic", "usage": {}, "local": True}
        finally:
            closed = True

    monkeypatch.setattr("plateforme.conversation_routes.flux_dialogue", generate)
    store = Conversations(application.state.depot)
    identifier = store.creer()["id"]
    body = json.dumps({"message": "Synthetic", "operation_id": str(uuid.uuid4())}).encode()
    scope = {
        "type": "http",
        "asgi": {"spec_version": "2.4"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": f"/api/conversations/{identifier}/messages",
        "query_string": b"",
        "headers": [
            (b"host", parametres.url.removeprefix("http://").encode()),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            (b"authorization", bearer["Authorization"].encode()),
        ],
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        if (
            message["type"] == "http.response.body"
            and message.get("body")
            and json.loads(message["body"])["type"] == failed_event
        ):
            raise OSError("Synthetic disconnected browser")

    with pytest.raises(ClientDisconnect):
        await application(scope, receive, send)
    measures = application.state.mesures
    assert closed and not application.state.moteur.inference.locked()
    assert measures.aura.labels("text", "cancelled")._value.get() == 1
    assert measures.aura.labels("text", "success")._value.get() == 0
    assert measures.aura.labels("text", "error")._value.get() == 0
    counts = [
        s.value for s in measures.first_token.collect()[0].samples if s.name.endswith("_count")
    ]
    assert sum(counts) == int(failed_event == "done")
    assert store.obtenir(identifier)["total_messages"] == (2 if failed_event == "done" else 0)


@pytest.mark.asyncio
async def test_cancelled_pending_inference_has_no_token_sample_or_partial_history(
    application, parametres, bearer, monkeypatch
):
    started, closed = asyncio.Event(), asyncio.Event()

    async def generate(*args, **kwargs):
        try:
            started.set()
            await asyncio.Event().wait()
            yield {"type": "token", "text": "unreachable"}
        finally:
            closed.set()

    monkeypatch.setattr("plateforme.conversation_routes.flux_dialogue", generate)
    store = Conversations(application.state.depot)
    identifier = store.creer()["id"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url=parametres.url
    ) as client:
        task = asyncio.create_task(
            client.post(
                f"/api/conversations/{identifier}/messages",
                headers=bearer,
                json={"message": "Synthetic", "operation_id": str(uuid.uuid4())},
            )
        )
        await asyncio.wait_for(started.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    measures = application.state.mesures
    assert closed.is_set() and not application.state.moteur.inference.locked()
    assert measures.aura.labels("text", "cancelled")._value.get() == 1
    assert measures.aura.labels("text", "success")._value.get() == 0
    assert not measures.first_token.collect()[0].samples
    assert store.obtenir(identifier)["total_messages"] == 0
