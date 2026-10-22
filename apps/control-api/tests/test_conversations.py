"""History is private, transactional, bounded and has no tool/approval authority."""

import base64
import json
import uuid

import pytest

from plateforme.conversations import Conversations
from plateforme.depot import Conflit, Introuvable


def turn():
    return {"message": "Synthetic question", "operation_id": str(uuid.uuid4()), "langue": "en"}


@pytest.fixture
def reply(monkeypatch):
    calls = []

    async def generate(p, messages, langue):
        calls.append((messages, langue))
        yield {"type": "token", "text": "Synthetic "}
        yield {"type": "token", "text": "answer."}
        yield {
            "type": "done",
            "texte": "Synthetic answer.",
            "usage": {"total_tokens": 24},
            "local": True,
            "actions_executees": False,
        }

    monkeypatch.setattr("plateforme.conversation_routes.flux_dialogue", generate)
    return calls


def test_history_requires_auth_for_every_route(client, bearer):
    created = client.post("/api/conversations", headers=bearer, json={}).json()
    identifier = created["id"]
    for method, url, body in [
        ("GET", "/api/conversations", None),
        ("GET", f"/api/conversations/{identifier}", None),
        ("POST", "/api/conversations", {}),
        ("PATCH", f"/api/conversations/{identifier}", {"titre": "x"}),
        ("DELETE", f"/api/conversations/{identifier}", {}),
        ("POST", f"/api/conversations/{identifier}/messages", turn()),
        ("POST", f"/api/conversations/{identifier}/pieces", {"nom": "x.txt", "contenu": "eA=="}),
    ]:
        assert client.request(method, url, json=body).status_code == 401


def test_history_stream_saves_atomic_pair_and_reuses_completed_request(
    client, bearer, application, reply
):
    created = client.post("/api/conversations", headers=bearer, json={}).json()
    identifier, body = created["id"], turn()
    response = client.post(f"/api/conversations/{identifier}/messages", headers=bearer, json=body)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["type"] for event in events] == ["token", "token", "done"]
    saved = client.get(f"/api/conversations/{identifier}", headers=bearer).json()
    assert [message["role"] for message in saved["messages"]] == ["user", "assistant"]
    assert saved["messages"][1]["content"] == "Synthetic answer."
    assert not application.state.moteur.inference.locked()
    again = client.post(f"/api/conversations/{identifier}/messages", headers=bearer, json=body)
    assert len(again.text.splitlines()) == 1
    assert len(reply) == 1
    assert (
        client.get(f"/api/conversations/{identifier}", headers=bearer).json()["total_messages"] == 2
    )
    results = client.get("/api/conversations?recherche=answer", headers=bearer).json()
    assert results["total"] == 1
    assert "Synthetic question" not in json.dumps(application.state.depot.journal())
    assert application.state.depot.statistiques()["total"] == 0


def test_failed_partial_reply_is_never_saved_and_releases_lock(
    client, bearer, application, monkeypatch
):
    async def interrupted(*args):
        yield {"type": "token", "text": "Unfinished"}
        raise ValueError("Private upstream diagnostic must never escape")

    monkeypatch.setattr("plateforme.conversation_routes.flux_dialogue", interrupted)
    identifier = client.post("/api/conversations", headers=bearer, json={}).json()["id"]
    result = client.post(f"/api/conversations/{identifier}/messages", headers=bearer, json=turn())
    assert json.loads(result.text.splitlines()[-1])["type"] == "error"
    assert "Private upstream" not in result.text
    assert (
        client.get(f"/api/conversations/{identifier}", headers=bearer).json()["total_messages"] == 0
    )
    assert not application.state.moteur.inference.locked()


def test_history_cannot_bypass_busy_engine_or_invent_system_roles(
    client, bearer, application, reply
):
    identifier = client.post("/api/conversations", headers=bearer, json={}).json()["id"]
    body = {**turn(), "role": "system"}
    assert (
        client.post(
            f"/api/conversations/{identifier}/messages", headers=bearer, json=body
        ).status_code
        == 422
    )
    application.state.moteur.creer("Synthetic", "Synthetic", "test")
    assert (
        client.post(
            f"/api/conversations/{identifier}/messages", headers=bearer, json=turn()
        ).status_code
        == 409
    )
    assert not reply


def test_attachment_is_scoped_to_its_conversation_and_deletion_is_complete(depot):
    store = Conversations(depot)
    first, second = store.creer(), store.creer()
    document = store.ajouter_piece(
        first["id"],
        "private.csv",
        {"kind": "text", "text": "name,value\nservice,42", "truncated": False},
    )
    with pytest.raises(Introuvable):
        store.contexte(second["id"], "Read", [document["id"]])
    with pytest.raises(Introuvable):
        store.retirer_piece(second["id"], document["id"])
    context = store.contexte(first["id"], "Read", [document["id"]])
    assert "UNTRUSTED DOCUMENT" in context[-1]["content"][1]["text"]
    store.enregistrer_tour(first["id"], str(uuid.uuid4()), "Question", {"texte": "Answer"})
    store.supprimer(first["id"])
    with depot.connexion() as c:
        assert c.execute("SELECT count(*) FROM pieces_conversation").fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM messages_conversation").fetchone()[0] == 0
    assert store.lister()["total"] == 1


def test_context_is_bounded_and_does_not_include_other_threads(depot):
    store = Conversations(depot)
    first, other = store.creer(), store.creer()
    store.enregistrer_tour(
        other["id"], str(uuid.uuid4()), "OTHER_PRIVATE_THREAD", {"texte": "Other"}
    )
    for _ in range(15):
        store.enregistrer_tour(first["id"], str(uuid.uuid4()), "q" * 4000, {"texte": "a" * 6000})
    context = store.contexte(first["id"], "Now", [])
    assert sum(len(item["content"]) for item in context[:-1]) <= 16_000
    assert len(context) <= 8
    assert "OTHER_PRIVATE_THREAD" not in json.dumps(context)
    assert context[-1] == {"role": "user", "content": "Now"}


def test_expiry_removes_messages_and_attachments_together(depot):
    store = Conversations(depot)
    identifier = store.creer()["id"]
    store.enregistrer_tour(
        identifier, str(uuid.uuid4()), "Old private text", {"texte": "Old reply"}
    )
    store.ajouter_piece(identifier, "old.txt", {"kind": "text", "text": "old", "truncated": False})
    with depot.connexion() as c:
        c.execute("UPDATE conversations SET maj_le='2000-01-01T00:00:00+00:00'")
    store.purger()
    assert store.lister()["total"] == 0
    with depot.connexion() as c:
        for table in ("pieces_conversation", "messages_conversation"):
            assert c.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_storage_quota_rolls_back_complete_turn(depot, monkeypatch):
    store = Conversations(depot)
    identifier = store.creer()["id"]
    monkeypatch.setattr("plateforme.conversations.MAX_STORAGE", 5)
    with pytest.raises(Conflit):
        store.enregistrer_tour(identifier, str(uuid.uuid4()), "Question", {"texte": "Answer"})
    assert store.obtenir(identifier)["total_messages"] == 0


def test_idempotency_rejects_changed_message_or_language_and_replays_while_busy(
    client, bearer, application, reply
):
    identifier = client.post("/api/conversations", headers=bearer, json={}).json()["id"]
    body = turn()
    url = f"/api/conversations/{identifier}/messages"
    assert client.post(url, headers=bearer, json=body).status_code == 200
    for change in [{"message": "Different"}, {"langue": "fr"}, {"pieces": [str(uuid.uuid4())]}]:
        assert client.post(url, headers=bearer, json={**body, **change}).status_code == 409
    application.state.moteur.creer("Synthetic", "Synthetic", "test")
    assert client.post(url, headers=bearer, json=body).status_code == 200
    assert len(reply) == 1


def test_multiple_large_documents_share_context_and_custom_title_survives(depot):
    store = Conversations(depot)
    identifier = store.creer("My client scope")["id"]
    ids = [
        store.ajouter_piece(
            identifier,
            f"part{index}.txt",
            {"kind": "text", "text": str(index) * 16000, "truncated": False},
        )["id"]
        for index in range(2)
    ]
    context = store.contexte(identifier, "Compare", ids)
    assert len(context[-1]["content"]) == 3
    assert all("Truncated: True" in document["text"] for document in context[-1]["content"][1:])
    assert "0" * 8000 in context[-1]["content"][1]["text"]
    assert "1" * 8000 in context[-1]["content"][2]["text"]
    store.enregistrer_tour(identifier, str(uuid.uuid4()), "Compare", {"texte": "Answer"})
    assert store.obtenir(identifier)["titre"] == "My client scope"


def test_document_upload_uses_real_isolated_parser(client, bearer):
    identifier = client.post("/api/conversations", headers=bearer, json={}).json()["id"]
    response = client.post(
        f"/api/conversations/{identifier}/pieces",
        headers=bearer,
        json={
            "nom": "metrics.csv",
            "contenu": base64.b64encode(b"service,latency_ms\ngateway,125").decode(),
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["kind"] == "text"
    assert "gateway,125" not in response.text
    listing = client.get(f"/api/conversations/{identifier}", headers=bearer).json()
    assert listing["pieces"][0]["nom"] == "metrics.csv"
    assert "gateway,125" not in json.dumps(listing)


@pytest.mark.parametrize(
    "body",
    [
        {"nom": "../secret.txt", "contenu": "eA=="},
        {"nom": "script.exe", "contenu": "eA=="},
        {"nom": "image.png", "contenu": "not-base64"},
    ],
)
def test_malformed_upload_rejected_without_persistence(client, bearer, body):
    identifier = client.post("/api/conversations", headers=bearer, json={}).json()["id"]
    assert client.post(
        f"/api/conversations/{identifier}/pieces", headers=bearer, json=body
    ).status_code in {415, 422}
    assert not client.get(f"/api/conversations/{identifier}", headers=bearer).json()["pieces"]


def test_spoken_reply_mode_is_strict_and_part_of_idempotency(client, bearer, monkeypatch):
    calls = []

    async def spoken(p, messages, langue, vocal=False):
        calls.append(vocal)
        yield {"type": "done", "texte": "Short reply.", "local": True, "actions_executees": False}

    monkeypatch.setattr("plateforme.conversation_routes.flux_dialogue", spoken)
    identifier = client.post("/api/conversations", headers=bearer, json={}).json()["id"]
    url = f"/api/conversations/{identifier}/messages"
    body = {**turn(), "vocal": True}
    result = client.post(url, headers=bearer, json=body)
    assert result.status_code == 200 and calls == [True]
    assert client.post(url, headers=bearer, json=body).status_code == 200
    assert calls == [True]
    assert client.post(url, headers=bearer, json={**body, "vocal": False}).status_code == 409
    assert client.post(url, headers=bearer, json={**turn(), "vocal": "true"}).status_code == 422


def test_production_dialogue_rate_limit_and_recovery(
    client, application, session, reply, monkeypatch
):
    import time
    from types import SimpleNamespace

    instant = 1000.0
    legacy_calls = []

    async def legacy_model(*args):
        legacy_calls.append(True)
        return {"texte": "Synthetic legacy answer", "local": True, "actions_executees": False}

    monkeypatch.setattr("plateforme.app.dialoguer", legacy_model)
    monkeypatch.setattr(
        "plateforme.securite.time", SimpleNamespace(monotonic=lambda: instant, time=time.time)
    )
    identifier = client.post("/api/conversations", headers=session, json={}).json()["id"]
    endpoint, body = f"/api/conversations/{identifier}/messages", turn()
    legacy = {"messages": [{"role": "user", "content": "Synthetic legacy request"}]}
    for index in range(8):
        response = client.post(
            "/api/assistant/dialogue" if index % 2 else endpoint,
            headers=session,
            json=legacy if index % 2 else body,
        )
        assert response.status_code == 200
    assert len(reply) == 1  # Completed retries only replay stored state.
    assert len(legacy_calls) == 4
    instant += 59
    denied = client.post(endpoint, headers=session, json=turn())
    assert denied.status_code == 429
    assert denied.headers["retry-after"] == "60"
    assert client.post("/api/assistant/dialogue", headers=session, json=legacy).status_code == 429
    assert len(reply) == 1
    assert len(legacy_calls) == 4
    assert (
        client.get(f"/api/conversations/{identifier}", headers=session).json()["total_messages"]
        == 2
    )
    instant += 2
    assert client.post(endpoint, headers=session, json=turn()).status_code == 200
    assert len(reply) == 2
    assert (
        client.get(f"/api/conversations/{identifier}", headers=session).json()["total_messages"]
        == 4
    )
    assert not application.state.moteur.inference.locked()
