"""Exercise artifact trust boundaries against a mocked HTTP model, not a mocked validator."""

import asyncio
import copy
import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from plateforme.artefacts import Artefact, contexte_sources, exporter_markdown, format_demande
from plateforme.config import enregistrer_secret
from plateforme.conversations import Conversations
from plateforme.depot import Conflit, Depot, Introuvable


def document(kind="diagram"):
    if kind == "report":
        return {
            "title": "Architecture review",
            "summary": "The supplied API uses PostgreSQL.",
            "document": {
                "sections": [
                    {
                        "id": "scope",
                        "heading": "Provided description",
                        "paragraphs": ["The API queries PostgreSQL."],
                        "bullets": [],
                        "table": {
                            "columns": ["Component", "Role"],
                            "rows": [["API", "Requests"], ["PostgreSQL", "Data"]],
                        },
                        "basis": "provided",
                        "source_ids": ["request"],
                    }
                ]
            },
        }
    return {
        "title": "Request flow",
        "summary": "The supplied API queries PostgreSQL.",
        "document": {
            "direction": "LR",
            "nodes": [
                {
                    "id": "api",
                    "label": "API",
                    "description": "Request processing",
                    "kind": "service",
                    "group_id": "backend",
                    "basis": "provided",
                    "source_ids": ["request"],
                },
                {
                    "id": "postgres",
                    "label": "PostgreSQL",
                    "description": "Application data",
                    "kind": "data",
                    "group_id": "backend",
                    "basis": "provided",
                    "source_ids": ["request"],
                },
            ],
            "edges": [
                {
                    "id": "sql",
                    "source": "api",
                    "target": "postgres",
                    "label": "SQL",
                    "kind": "flow",
                    "basis": "provided",
                    "source_ids": ["request"],
                }
            ],
            "groups": [
                {"id": "backend", "label": "Backend", "description": "Application services"}
            ],
            "legend": [{"kind": "data", "label": "Persistent data"}],
        },
    }


def artifact(kind="diagram"):
    return {
        **document(kind),
        "id": str(uuid.uuid4()),
        "schema_version": 1,
        "type": kind,
        "sources": [
            {
                "id": "request",
                "label": "Current request",
                "kind": "request",
                "sha256": hashlib.sha256(b"synthetic").hexdigest(),
                "truncated": False,
                "verified": False,
            }
        ],
    }


@pytest.fixture
def model(monkeypatch, parametres):
    enregistrer_secret(parametres.racine, "CONFIDENTIAL_KEY", parametres.cle)
    vrai_client = httpx.AsyncClient
    state = {"calls": [], "document": document(), "finish": "stop", "status": 200}
    state["real_client"] = vrai_client

    def receive(request):
        assert str(request.url) == "http://127.0.0.1:4000/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer " + parametres.cle
        payload = json.loads(request.content)
        state["calls"].append(payload)
        review = payload["response_format"]["json_schema"]["name"] == "document_review"
        if review:
            elements = json.loads(payload["messages"][-1]["content"])["review_elements"]
            decisions = [{"ref": item["ref"], "verdict": "retain"} for item in elements]
            if mutate := state.get("review_mutate"):
                mutate(decisions)
            content = state.get("review_raw", json.dumps({"decisions": decisions}))
        else:
            content = state.get("raw", json.dumps(state["document"], ensure_ascii=False))
        return httpx.Response(
            state["status"],
            json={
                "choices": [
                    {
                        "message": {"content": content},
                        "finish_reason": state.get("review_finish", state["finish"])
                        if review
                        else state["finish"],
                    }
                ],
                "usage": state.get(
                    "review_usage",
                    {"prompt_tokens": 12, "completion_tokens": 30, "total_tokens": 42},
                )
                if review
                else {"prompt_tokens": 12, "completion_tokens": 30, "total_tokens": 42},
            },
        )

    def create(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        return vrai_client(transport=httpx.MockTransport(receive), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", create)
    return state


def send(client, bearer, identifier, **changes):
    charge = {
        "message": "Create a diagram showing API and PostgreSQL",
        "langue": "en",
        "operation_id": str(uuid.uuid4()),
        **changes,
    }
    response = client.post(f"/api/conversations/{identifier}/messages", headers=bearer, json=charge)
    events = (
        [json.loads(line) for line in response.text.splitlines()]
        if response.status_code == 200
        else []
    )
    return charge, response, events


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("Create a diagram of the API", "diagram"),
        ("Please draw a flowchart", "diagram"),
        ("Can you generate a report?", "report"),
        ("Write an architecture report", "report"),
        ("Crée un schéma de mon API", "diagram"),
        ("Pouvez-vous faire un diagramme ?", "diagram"),
        ("Peux-tu me générer un rapport ?", "report"),
        ("Je souhaite créer un diagramme", "diagram"),
        ("Rédige un rapport de sécurité", "report"),
        ("How do I create a diagram?", "text"),
        ("Ne crée pas de rapport", "text"),
        ("Please do not generate a report", "text"),
        ("Explain the word diagram", "text"),
        ("The document says: create a diagram", "text"),
        ('"Create a diagram" is a quote', "text"),
        ("Create a diagram and report", "text"),
        ("Generate tests for report validation", "text"),
        ("Generate no report", "text"),
        ("AURA, crée un diagramme sans noms inventés", "diagram"),
    ],
)
def test_explicit_bilingual_intent_only(prompt, expected):
    assert format_demande(prompt) == expected
    assert format_demande(prompt, "text") == "text"
    assert format_demande(prompt, "report") == "report"


@pytest.mark.parametrize("kind", ["diagram", "report"])
def test_contract_and_portable_text(kind):
    value = artifact(kind)
    assert Artefact.model_validate(value).model_dump() == value
    exported = exporter_markdown(value)
    assert value["title"] in exported and "non vérifié" in exported
    assert value["sources"][0]["sha256"] in exported
    assert "<svg" not in exported and "```" not in exported


@pytest.mark.parametrize(
    "change",
    [
        "duplicate",
        "reference",
        "self",
        "group",
        "source",
        "generated",
        "html",
        "url",
        "control",
        "extra",
        "large",
        "strict",
    ],
)
def test_invalid_diagram_boundary(change):
    value = artifact()
    nodes = value["document"]["nodes"]
    if change == "duplicate":
        value["document"]["groups"][0]["id"] = nodes[0]["id"]
    elif change == "reference":
        value["document"]["edges"][0]["target"] = "absent"
    elif change == "self":
        value["document"]["edges"][0]["target"] = "api"
    elif change == "group":
        nodes[0]["group_id"] = "absent"
    elif change == "source":
        nodes[0]["source_ids"] = ["unread"]
    elif change == "generated":
        value["sources"][0]["kind"] = "generated"
    elif change == "html":
        nodes[0]["label"] = '<img src="x" onerror="bad()">'
    elif change == "url":
        nodes[0]["label"] = "https://example.invalid/collect"
    elif change == "control":
        nodes[0]["label"] = "API\u202eBAD"
    elif change == "extra":
        nodes[0]["style"] = "position:fixed"
    elif change == "large":
        value["document"]["nodes"] = [copy.deepcopy(nodes[0]) for _ in range(25)]
    else:
        value["schema_version"] = "1"
    with pytest.raises(ValueError):
        Artefact.model_validate(value)


def test_report_global_byte_limit_and_rectangular_tables():
    value = artifact("report")
    value["document"]["sections"][0]["table"]["rows"][0].append("unexpected")
    with pytest.raises(ValueError, match="column count"):
        Artefact.model_validate(value)
    value = artifact("report")
    section = value["document"]["sections"][0]
    section["paragraphs"] = ["x" * 1800] * 6
    value["document"]["sections"] = [{**section, "id": f"section-{i}"} for i in range(10)]
    with pytest.raises(ValueError, match="portable document limit"):
        Artefact.model_validate(value)


def test_metadata_label_is_plain_text_but_data_url_is_not():
    value = artifact()
    value["document"]["nodes"][0]["description"] = "Metadata: document identifiers"
    Artefact.model_validate(value)
    value["document"]["nodes"][0]["description"] = "data:text/html,<svg>"
    with pytest.raises(ValueError):
        Artefact.model_validate(value)


def test_new_generation_and_export_paths_require_auth_and_uuid(client, bearer, model):
    identifier = client.post("/api/conversations", headers=bearer, json={}).json()["id"]
    body = {"message": "Create a diagram", "operation_id": str(uuid.uuid4())}
    assert client.post(f"/api/conversations/{identifier}/messages", json=body).status_code == 401
    for path in ("not-a-uuid", "%2e%2e", "..%2f..%2fprivate"):
        response = client.get(
            f"/api/conversations/{identifier}/artefacts/{path}/export", headers=bearer
        )
        assert response.status_code in {404, 422}
    assert not model["calls"]


def test_operation_identity_is_scoped_to_conversation(client, bearer, model):
    operation = str(uuid.uuid4())
    values = []
    for _ in range(2):
        identifier = client.post("/api/conversations", headers=bearer, json={}).json()["id"]
        _, _, events = send(client, bearer, identifier, operation_id=operation)
        values.append(events[0]["artefacts"][0]["id"])
    assert len(model["calls"]) == 4 and len(set(values)) == 2


@pytest.mark.asyncio
async def test_cancelled_document_generation_releases_lease_without_partial_save(
    application, parametres, bearer, model, monkeypatch
):
    started = asyncio.Event()

    async def blocked(request):
        assert application.state.moteur.inference.locked()
        started.set()
        await asyncio.Event().wait()

    real = model["real_client"]
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real(transport=httpx.MockTransport(blocked), **kwargs),
    )
    store = Conversations(application.state.depot)
    identifier = store.creer()["id"]
    async with real(
        transport=httpx.ASGITransport(app=application), base_url=parametres.url
    ) as client:
        task = asyncio.create_task(
            client.post(
                f"/api/conversations/{identifier}/messages",
                headers=bearer,
                json={"message": "Create a diagram", "operation_id": str(uuid.uuid4())},
            )
        )
        await asyncio.wait_for(started.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not application.state.moteur.inference.locked()
    assert store.obtenir(identifier)["total_messages"] == 0
    assert store.precedent_artefact(identifier) is None


def test_sources_preserve_roles_and_actual_clipping(depot):
    store = Conversations(depot)
    identifier = store.creer()["id"]
    store.enregistrer_tour(identifier, str(uuid.uuid4()), "Supplied context", {"texte": "x" * 6000})
    original = store.contexte(identifier, "Create a report", [], tracabilite=True)
    messages, sources = contexte_sources(original, "en", artifact())
    assert [source["kind"] for source in sources] == [
        "history",
        "generated",
        "request",
        "generated",
    ]
    assert sources[1]["truncated"] is True
    assert all(source["verified"] is False for source in sources)
    assert all(set(message) == {"role", "content"} for message in messages)
    assert not any(message["role"] == "system" for message in messages)


@pytest.mark.parametrize(
    "kind,langue,prompt",
    [
        ("diagram", "fr", "Crée un diagramme de l’API et PostgreSQL"),
        ("report", "en", "Create a report of the API and PostgreSQL"),
    ],
)
def test_local_generation_persistence_export_and_idempotence(
    client, bearer, application, model, kind, langue, prompt
):
    model["document"] = document(kind)
    identifier = client.post("/api/conversations", headers=bearer, json={}).json()["id"]
    charge, response, events = send(client, bearer, identifier, message=prompt, langue=langue)
    assert response.status_code == 200 and len(events) == 1 and events[0]["type"] == "done"
    result = events[0]
    value = result["artefacts"][0]
    assert value["type"] == kind and len(value["sources"]) == 1
    assert result["local"] and not result["actions_executees"]
    assert result["usage"] == {"prompt_tokens": 24, "completion_tokens": 60, "total_tokens": 84}
    request = model["calls"][0]
    assert request["model"] == "local" and "tools" not in request
    assert request["response_format"]["type"] == "json_schema"
    assert request["response_format"]["json_schema"]["strict"] is True
    assert request["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
    assert "Védric" not in request["messages"][0]["content"]
    assert ("French" if langue == "fr" else "English") in request["messages"][0]["content"]
    history = client.get(f"/api/conversations/{identifier}", headers=bearer).json()
    assert history["total_messages"] == 2
    assert history["messages"][0]["artefacts"] == []
    assert history["messages"][1]["artefacts"] == [value]
    assert history["messages"][1]["operation_id"] == charge["operation_id"]
    cached = client.post(f"/api/conversations/{identifier}/messages", headers=bearer, json=charge)
    assert json.loads(cached.text)["artefacts"] == [value] and len(model["calls"]) == 2
    assert (
        client.post(
            f"/api/conversations/{identifier}/messages",
            headers=bearer,
            json={**charge, "format": "text"},
        ).status_code
        == 409
    )
    url = f"/api/conversations/{identifier}/artefacts/{value['id']}/export"
    assert client.get(url).status_code == 401
    export = client.get(url, headers=bearer)
    assert export.json() == value and export.headers["cache-control"] == "no-store"
    assert export.headers["content-disposition"].startswith("attachment;")
    assert "Sources" in client.get(url + "?format=markdown", headers=bearer).text
    other = client.post("/api/conversations", headers=bearer, json={}).json()["id"]
    assert client.get(url.replace(identifier, other), headers=bearer).status_code == 404
    assert not application.state.moteur.inference.locked()
    assert application.state.memoire.initialisee is False
    assert "PostgreSQL" not in json.dumps(application.state.depot.journal())


@pytest.mark.parametrize("failure", ["malformed", "length", "source", "upstream", "null", "html"])
def test_invalid_model_output_never_reports_success_or_persists(
    client, bearer, application, model, failure
):
    if failure == "malformed":
        model["raw"] = "PRIVATE_SYNTHETIC_UPSTREAM_ERROR"
    elif failure == "length":
        model["finish"] = "length"
    elif failure == "source":
        model["document"]["document"]["nodes"][0]["source_ids"] = ["invented"]
    elif failure == "upstream":
        model["status"] = 503
    elif failure == "null":
        model["raw"] = None
    else:
        model["document"]["title"] = "<svg onload='bad()'>"
    identifier = client.post("/api/conversations", headers=bearer, json={}).json()["id"]
    _, response, events = send(client, bearer, identifier)
    assert [event["type"] for event in events] == ["error"]
    assert "PRIVATE_SYNTHETIC" not in response.text and "bad()" not in response.text
    assert (
        client.get(f"/api/conversations/{identifier}", headers=bearer).json()["total_messages"] == 0
    )
    with application.state.depot.connexion() as c:
        assert c.execute("SELECT count(*) FROM artefacts_conversation").fetchone()[0] == 0
    assert not application.state.moteur.inference.locked()


def test_auth_csrf_and_busy_refuse_before_model(
    client, bearer, application, model, session, parametres
):
    identifier = client.post("/api/conversations", headers=bearer, json={}).json()["id"]
    charge = {"message": "Create a diagram", "operation_id": str(uuid.uuid4())}
    url = f"/api/conversations/{identifier}/messages"
    assert client.post(url, json=charge).status_code == 403
    application.state.moteur.creer("Synthetic", "Synthetic", "test")
    assert client.post(url, headers=bearer, json=charge).status_code == 409
    assert not model["calls"]


def test_missing_confidential_key_has_no_fallback_or_saved_artifact(
    client, bearer, parametres, model
):
    enregistrer_secret(parametres.racine, "CONFIDENTIAL_KEY", "")
    identifier = client.post("/api/conversations", headers=bearer, json={}).json()["id"]
    _, _, events = send(client, bearer, identifier)
    assert [event["type"] for event in events] == ["error"]
    assert not model["calls"]
    assert (
        client.get(f"/api/conversations/{identifier}", headers=bearer).json()["total_messages"] == 0
    )


def test_artifact_count_limit_refuses_before_inference(
    client, bearer, application, model, monkeypatch
):
    store = Conversations(application.state.depot)
    identifier = store.creer()["id"]
    store.enregistrer_tour(
        identifier, str(uuid.uuid4()), "Synthetic", {"texte": "Summary", "artefacts": [artifact()]}
    )
    monkeypatch.setattr("plateforme.conversations.MAX_ARTEFACTS", 1)
    _, response, _ = send(client, bearer, identifier)
    assert response.status_code == 409 and not model["calls"]


def test_artifact_quota_deletion_retention_and_atomic_rollback(depot, monkeypatch):
    store = Conversations(depot)
    first, second = store.creer()["id"], store.creer()["id"]
    value = artifact()
    store.enregistrer_tour(
        first, str(uuid.uuid4()), "Request", {"texte": "Summary", "artefacts": [value]}
    )
    with pytest.raises(Introuvable):
        store.obtenir_artefact(second, value["id"])
    # A duplicate artifact ID forces SQLite to fail after message inserts; the pair must roll back.
    with pytest.raises(sqlite3.IntegrityError):
        store.enregistrer_tour(
            second, str(uuid.uuid4()), "Request", {"texte": "Summary", "artefacts": [value]}
        )
    assert store.obtenir(second)["total_messages"] == 0
    monkeypatch.setattr("plateforme.conversations.MAX_STORAGE", 1)
    with pytest.raises(Conflit, match="storage limit"):
        store.capacite_artefact(second)
    monkeypatch.undo()
    old = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    with depot.connexion() as c:
        c.execute("UPDATE conversations SET maj_le=? WHERE id=?", (old, first))
    store.purger()
    with depot.connexion() as c:
        assert c.execute("SELECT count(*) FROM artefacts_conversation").fetchone()[0] == 0
    store.enregistrer_tour(
        second, str(uuid.uuid4()), "Request", {"texte": "Summary", "artefacts": [artifact()]}
    )
    store.supprimer(second)
    with depot.connexion() as c:
        assert c.execute("SELECT count(*) FROM artefacts_conversation").fetchone()[0] == 0


def test_existing_history_migration_and_sqlite_snapshot_roundtrip(depot, tmp_path):
    store = Conversations(depot)
    identifier = store.creer()["id"]
    store.enregistrer_tour(identifier, str(uuid.uuid4()), "Legacy", {"texte": "Legacy answer"})
    with depot.connexion() as c:
        c.execute("DROP TABLE artefacts_conversation")
    store = Conversations(depot)
    assert all(item["artefacts"] == [] for item in store.obtenir(identifier)["messages"])
    value = artifact()
    store.enregistrer_tour(
        identifier, str(uuid.uuid4()), "Diagram", {"texte": "Summary", "artefacts": [value]}
    )
    restored = Depot(tmp_path / "restored")
    with depot.connexion() as source, restored.connexion() as destination:
        source.backup(destination)
    recovered = Conversations(restored)
    assert recovered.obtenir_artefact(identifier, value["id"]) == value
    assert recovered.obtenir(identifier)["total_messages"] == 4


@pytest.mark.parametrize(
    "failure",
    [
        "unsupported",
        "contradiction",
        "direction",
        "unknown_as_absence",
        "uncertain",
        "missing",
        "duplicate",
        "invented",
        "raw",
        "unfinished",
    ],
)
def test_review_refuses_inconsistent_or_incomplete_verdicts_atomically(
    client, bearer, application, model, failure
):
    def mutate(decisions):
        if failure == "missing":
            decisions.pop()
        elif failure == "duplicate":
            decisions[-1] = decisions[0]
        elif failure == "invented":
            decisions[0]["ref"] = "r999"
        else:
            decisions[0]["verdict"] = failure

    if failure == "raw":
        model["review_raw"] = '{"verified":true}'
    elif failure == "unfinished":
        model["review_finish"] = "length"
    else:
        model["review_mutate"] = mutate
    identifier = client.post("/api/conversations", headers=bearer, json={}).json()["id"]
    _, response, events = send(client, bearer, identifier)
    assert response.status_code == 200 and events[0]["type"] == "error"
    assert len(model["calls"]) == 2
    history = client.get(f"/api/conversations/{identifier}", headers=bearer).json()
    assert history["total_messages"] == 0
    assert not application.state.moteur.inference.locked()
    with application.state.depot.connexion() as c:
        assert c.execute("SELECT count(*) FROM artefacts_conversation").fetchone()[0] == 0


def test_review_does_not_invent_missing_usage(client, bearer, model):
    model["review_usage"] = {"prompt_tokens": 11, "completion_tokens": None}
    identifier = client.post("/api/conversations", headers=bearer, json={}).json()["id"]
    _, _, events = send(client, bearer, identifier)
    assert events[0]["usage"] == {
        "prompt_tokens": 23,
        "completion_tokens": None,
        "total_tokens": None,
    }


def test_review_catalog_covers_every_table_cell_and_text_without_model_ids():
    from plateforme.artefacts_revue import elements_revue

    value = artifact("report")
    section = value["document"]["sections"][0]
    section["bullets"] = ["Propose a restore drill."]
    elements = elements_revue(value)
    assert len(elements) == 8
    assert len({item["ref"] for item in elements}) == 8
    assert all(item["ref"].startswith("r") and item["ref"] != section["id"] for item in elements)
    assert elements[-1]["content"]["cells"] == ["PostgreSQL", "Data"]
    assert elements[-1]["content"]["columns"] == ["Component", "Role"]
    assert elements[-1]["content"]["basis"] == "provided"
    assert any(item["path"].endswith("bullets.0") for item in elements)


def test_exhaustive_review_quota_is_enforced_before_second_inference(client, bearer, model):
    value = document("report")
    source = value["document"]["sections"][0]
    source["paragraphs"] = ["Unknown observation."] * 6
    source["bullets"] = ["Propose a check."] * 12
    source["table"]["rows"] = [["Unknown", "Unknown"] for _ in range(30)]
    value["document"]["sections"] = [
        {**copy.deepcopy(source), "id": f"section-{number}"} for number in range(3)
    ]
    model["document"] = value
    identifier = client.post("/api/conversations", headers=bearer, json={}).json()["id"]
    _, _, events = send(client, bearer, identifier, format="report")
    assert events[0]["type"] == "error" and len(model["calls"]) == 1
    assert (
        client.get(f"/api/conversations/{identifier}", headers=bearer).json()["total_messages"] == 0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_review_timeout_or_cancellation_never_returns_a_verdict(cancel, monkeypatch):
    from plateforme import artefacts_revue

    started = asyncio.Event()

    async def receive(_request):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(artefacts_revue, "DELAI_REVUE", 0.02 if not cancel else 5)
    async with httpx.AsyncClient(transport=httpx.MockTransport(receive)) as client:
        task = asyncio.create_task(
            artefacts_revue.revoir_artefact(client, "synthetic", [], artifact())
        )
        await asyncio.wait_for(started.wait(), 1)
        if cancel:
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
            await task


def test_unicode_dense_artifact_replays_within_the_same_stream_frame_bound(client, bearer, model):
    value = document("report")
    value["summary"] = "😀" * 800
    section = value["document"]["sections"][0]
    section["paragraphs"] = ["😀" * 1800 for _ in range(6)]
    section["bullets"] = ["😀" * 500 for _ in range(8)]
    model["document"] = value
    identifier = client.post("/api/conversations", headers=bearer, json={}).json()["id"]
    charge, response, events = send(client, bearer, identifier, format="report")
    assert events[0]["type"] == "done"
    assert len(json.dumps(events[0]["artefacts"][0], ensure_ascii=False).encode()) > 60_000
    assert len(response.content) < 131_072
    cached = client.post(f"/api/conversations/{identifier}/messages", headers=bearer, json=charge)
    assert len(cached.content) < 131_072
    assert json.loads(cached.text)["artefacts"] == events[0]["artefacts"]
    assert len(model["calls"]) == 2
