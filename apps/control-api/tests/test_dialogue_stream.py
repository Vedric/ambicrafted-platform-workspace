import asyncio
import json

import httpx
import pytest
from starlette.requests import ClientDisconnect

from plateforme.assistant import flux_dialogue
from plateforme.conversation_routes import ReponseDialogue


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_at", ["headers", "body"])
async def test_disconnected_browser_releases_inference_even_before_first_token(failure_at):
    lock = asyncio.Lock()
    await lock.acquire()
    entered, closed = [], []

    async def events():
        try:
            entered.append(True)
            yield "synthetic token\n"
            await asyncio.sleep(60)
        finally:
            closed.append(True)

    async def receive():
        await asyncio.sleep(60)

    async def send(message):
        if message["type"] == (
            "http.response.start" if failure_at == "headers" else "http.response.body"
        ):
            raise OSError("Synthetic disconnected socket")

    response = ReponseDialogue(events(), lock)
    with pytest.raises(ClientDisconnect):
        await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
    assert not lock.locked()
    assert entered == closed


class Fragments(httpx.AsyncByteStream):
    def __init__(self, fragments):
        self.fragments = fragments
        self.closed = False

    async def __aiter__(self):
        for fragment in self.fragments:
            if isinstance(fragment, Exception):
                raise fragment
            yield fragment

    async def aclose(self):
        self.closed = True


def transport(monkeypatch, fragments):
    stream = Fragments(fragments)
    requests = []
    actual = httpx.AsyncClient

    def handler(request):
        requests.append(request)
        return httpx.Response(200, stream=stream)

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: actual(transport=httpx.MockTransport(handler), **kw)
    )
    return requests, stream


def token(text):
    return (
        "data: "
        + json.dumps({"choices": [{"delta": {"content": text}}]}, ensure_ascii=False)
        + "\n\n"
    ).encode()


@pytest.mark.asyncio
async def test_unicode_split_frames_usage_and_no_tool_authority(parametres, monkeypatch):
    data = (
        token("Bonjour, Védric.")
        + b'data: {"choices":[],"usage":{"total_tokens":19}}\n\ndata: [DONE]\n\n'
    )
    requests, stream = transport(
        monkeypatch, [data[index : index + 1] for index in range(len(data))]
    )
    events = [
        event
        async for event in flux_dialogue(parametres, [{"role": "user", "content": "Bonjour"}], "fr")
    ]
    assert events[0] == {"type": "token", "text": "Bonjour, Védric."}
    assert events[-1]["usage"]["total_tokens"] == 19
    body = json.loads(requests[0].content)
    assert body["model"] == "local" and body["stream"] is True
    assert "tools" not in body and "reasoning_content" not in str(events)
    assert stream.closed


@pytest.mark.asyncio
async def test_large_transport_chunk_with_small_frames_is_valid(parametres, monkeypatch):
    data = token("x") * 1500 + b"data: [DONE]\n\n"
    assert len(data) > 65536
    transport(monkeypatch, [data])
    events = [event async for event in flux_dialogue(parametres, [])]
    assert events[-1]["texte"] == "x" * 1500


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data",
    [
        token("Partial"),
        b"data: [DONE]\n\n",
        b"data: not json\n\n",
        b'data: {"choices":{}}\n\n',
        b'data: {"choices":[{"delta":42}]}\n\n',
        b'data: {"error":"private upstream detail"}\n\n',
        b"data: " + b"x" * 65536,
        token("x" * 6001) + b"data: [DONE]\n\n",
        b"x" * 1_000_001,
    ],
)
async def test_malformed_incomplete_and_oversized_streams_never_finish(
    parametres, monkeypatch, data
):
    _, stream = transport(monkeypatch, [data])
    collected = []
    with pytest.raises((ValueError, TypeError)):
        async for event in flux_dialogue(parametres, []):
            collected.append(event)
    assert not any(event["type"] == "done" for event in collected)
    assert stream.closed


@pytest.mark.asyncio
async def test_cancellation_closes_upstream_connection(parametres, monkeypatch):
    _, stream = transport(monkeypatch, [token("Starting"), token("Continuing")])
    generator = flux_dialogue(parametres, [])
    assert (await anext(generator))["type"] == "token"
    with pytest.raises(asyncio.CancelledError):
        await generator.athrow(asyncio.CancelledError())
    assert stream.closed
