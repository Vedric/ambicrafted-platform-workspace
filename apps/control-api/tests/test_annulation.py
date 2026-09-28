import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from plateforme.annulation import avec_connexion


@pytest.mark.asyncio
async def test_disconnect_cancels_work_and_runs_resource_cleanup():
    cleanup = asyncio.Event()

    async def work():
        try:
            await asyncio.sleep(30)
        finally:
            cleanup.set()

    request = AsyncMock()
    request.receive.return_value = {"type": "http.disconnect"}
    with pytest.raises(HTTPException) as error:
        await avec_connexion(request, work())
    assert error.value.status_code == 499
    assert cleanup.is_set()


@pytest.mark.asyncio
async def test_completed_work_and_errors_are_preserved_without_background_tasks():
    request = AsyncMock()

    async def connected():
        await asyncio.sleep(30)
        return {"type": "http.disconnect"}

    request.receive.side_effect = connected

    async def work():
        return "synthetic"

    assert await avec_connexion(request, work()) == "synthetic"

    async def fail():
        raise ValueError("synthetic")

    with pytest.raises(ValueError, match="synthetic"):
        await avec_connexion(request, fail())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route,body",
    [
        ("/api/voix/transcrire", {"audio": "UklGRg=="}),
        ("/api/voix/parler", {"texte": "Synthetic speech"}),
        ("/api/assistant/preparer", {}),
    ],
)
async def test_real_asgi_disconnect_releases_operation(
    application, parametres, monkeypatch, route, body
):
    import json

    started, closed = asyncio.Event(), asyncio.Event()

    async def slow(*args):
        started.set()
        try:
            await asyncio.sleep(60)
        finally:
            closed.set()

    if route.endswith("preparer"):
        monkeypatch.setattr("plateforme.app.preparer_dialogue", slow)
    else:
        monkeypatch.setattr(application.state.voix, route.rsplit("/", 1)[-1], slow)
    payload = json.dumps(body).encode()
    events = asyncio.Queue()
    await events.put({"type": "http.request", "body": payload, "more_body": False})

    async def send(message):
        pass

    task = asyncio.create_task(
        application(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.3"},
                "method": "POST",
                "scheme": "http",
                "path": route,
                "raw_path": route.encode(),
                "query_string": b"",
                "root_path": "",
                "server": ("127.0.0.1", parametres.port),
                "client": ("127.0.0.1", 50000),
                "headers": [
                    (b"host", f"127.0.0.1:{parametres.port}".encode()),
                    (b"authorization", ("Bearer " + parametres.cle).encode()),
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode()),
                ],
            },
            events.get,
            send,
        )
    )
    try:
        await asyncio.wait_for(started.wait(), 2)
        await events.put({"type": "http.disconnect"})
        await asyncio.wait_for(task, 2)
        assert closed.is_set()
        assert not application.state.moteur.inference.locked()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
