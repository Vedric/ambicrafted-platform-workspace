"""Real ASGI/auth/SQLite interactions with only the inference boundary substituted."""

import asyncio
import json
import uuid

import httpx
import pytest
from starlette.requests import ClientDisconnect


class StreamRequest:
    def __init__(self, application, parametres, headers, path, body, fail_on=None):
        self.application = application
        self.body = json.dumps(body).encode()
        self.scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "server": ("127.0.0.1", parametres.port),
            "client": ("127.0.0.1", 50000),
            "headers": [
                (b"host", f"127.0.0.1:{parametres.port}".encode()),
                (b"content-type", b"application/json"),
                (b"content-length", str(len(self.body)).encode()),
                *((k.lower().encode(), v.encode()) for k, v in headers.items()),
            ],
        }
        self.frames = []
        self.status = None
        self.fail_on = fail_on

    async def run(self):
        async def receive():
            body, self.body = self.body, b""
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                self.status = message["status"]
            elif message["type"] == "http.response.body" and message.get("body"):
                event = json.loads(message["body"])
                if event["type"] == self.fail_on:
                    raise OSError("Synthetic browser connection lost")
                self.frames.append(event)

        await self.application(self.scope, receive, send)


def payload():
    return {"message": "Synthetic concurrent request", "operation_id": str(uuid.uuid4())}


@pytest.mark.asyncio
async def test_two_clients_reject_inflight_duplicate_then_replay_one_saved_pair(
    application, parametres, bearer, monkeypatch
):
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def model(*args):
        calls.append(True)
        started.set()
        await release.wait()
        yield {"type": "done", "texte": "One saved answer", "local": True}

    monkeypatch.setattr("plateforme.conversation_routes.flux_dialogue", model)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url=parametres.url, headers=bearer
    ) as client:
        identifier = (await client.post("/api/conversations", json={})).json()["id"]
        route, body = f"/api/conversations/{identifier}/messages", payload()
        stream = StreamRequest(application, parametres, bearer, route, body)
        task = asyncio.create_task(stream.run())
        try:
            await asyncio.wait_for(started.wait(), 2)
            duplicate = await client.post(route, json=body)
            assert duplicate.status_code == 409
            assert len(calls) == 1
            assert (await client.get(f"/api/conversations/{identifier}")).json()[
                "total_messages"
            ] == 0
            release.set()
            await asyncio.wait_for(task, 2)
            retry = await client.post(route, json=body)
            assert [json.loads(line)["type"] for line in retry.text.splitlines()] == ["done"]
            changed = await client.post(route, json={**body, "message": "Different request"})
            assert changed.status_code == 409
            assert len(calls) == 1
            assert (await client.get(f"/api/conversations/{identifier}")).json()[
                "total_messages"
            ] == 2
            assert not application.state.moteur.inference.locked()
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("disconnect_at,expected_calls", [("token", 2), ("done", 1)])
async def test_disconnect_retry_before_and_after_commit_never_loses_or_duplicates_turn(
    application, parametres, bearer, monkeypatch, disconnect_at, expected_calls
):
    calls, closed = [], []

    async def model(*args):
        calls.append(True)
        try:
            yield {"type": "token", "text": "Saved answer"}
            yield {"type": "done", "texte": "Saved answer", "local": True}
        finally:
            closed.append(True)

    monkeypatch.setattr("plateforme.conversation_routes.flux_dialogue", model)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url=parametres.url, headers=bearer
    ) as client:
        identifier = (await client.post("/api/conversations", json={})).json()["id"]
        route, body = f"/api/conversations/{identifier}/messages", payload()
        stream = StreamRequest(application, parametres, bearer, route, body, disconnect_at)
        with pytest.raises(ClientDisconnect):
            await stream.run()
        assert not application.state.moteur.inference.locked()
        assert len(closed) == 1
        stored = (await client.get(f"/api/conversations/{identifier}")).json()
        assert stored["total_messages"] == (0 if disconnect_at == "token" else 2)
        retry = await client.post(route, json=body)
        assert retry.status_code == 200
        assert json.loads(retry.text.splitlines()[-1])["texte"] == "Saved answer"
        assert len(calls) == len(closed) == expected_calls
        stored = (await client.get(f"/api/conversations/{identifier}")).json()
        assert stored["total_messages"] == 2
        assert [message["operation_id"] for message in stored["messages"]] == [
            body["operation_id"]
        ] * 2


@pytest.mark.asyncio
async def test_other_tab_deletes_conversation_during_generation_without_resurrecting_history(
    application, parametres, bearer, monkeypatch
):
    started, release = asyncio.Event(), asyncio.Event()

    async def model(*args):
        yield {"type": "token", "text": "Uncommitted"}
        started.set()
        await release.wait()
        yield {"type": "done", "texte": "Uncommitted", "local": True}

    monkeypatch.setattr("plateforme.conversation_routes.flux_dialogue", model)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url=parametres.url, headers=bearer
    ) as client:
        identifier = (await client.post("/api/conversations", json={})).json()["id"]
        stream = StreamRequest(
            application, parametres, bearer, f"/api/conversations/{identifier}/messages", payload()
        )
        task = asyncio.create_task(stream.run())
        try:
            await asyncio.wait_for(started.wait(), 2)
            assert (
                await client.delete(
                    f"/api/conversations/{identifier}", headers={"Content-Type": "application/json"}
                )
            ).status_code == 200
            release.set()
            await asyncio.wait_for(task, 2)
            assert [event["type"] for event in stream.frames] == ["token", "error"]
            assert (await client.get(f"/api/conversations/{identifier}")).status_code == 404
            with application.state.depot.connexion() as connection:
                for table in (
                    "messages_conversation",
                    "requetes_conversation",
                    "artefacts_conversation",
                ):
                    assert connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
            assert not application.state.moteur.inference.locked()
            replacement = (await client.post("/api/conversations", json={})).json()["id"]
            retry = await client.post(f"/api/conversations/{replacement}/messages", json=payload())
            assert json.loads(retry.text.splitlines()[-1])["type"] == "done"
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)
