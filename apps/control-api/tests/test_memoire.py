import json
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from plateforme.config import enregistrer_secret
from plateforme.memoire import Lien, Memoire, Note


def test_memory_requires_auth_and_explicit_scope(client, bearer):
    identifier = str(uuid4())
    for method, path, body in [
        ("GET", "/api/memoire/statut", None),
        ("GET", "/api/memoire?scope=personal", None),
        (
            "POST",
            "/api/memoire",
            {"scope": "personal", "titre": "Test", "contenu": "Test", "source": "Test"},
        ),
        ("DELETE", f"/api/memoire/{identifier}?scope=personal", {}),
    ]:
        assert client.request(method, path, json=body).status_code == 401
    assert client.get("/api/memoire", headers=bearer).status_code == 422
    assert client.get("/api/memoire?scope=other/client", headers=bearer).status_code == 422
    assert client.get("/api/memoire/statut", headers=bearer).json()["ready"] is False


@pytest.mark.asyncio
async def test_graph_queries_use_fixed_local_destination_and_bound_parameters(
    parametres, monkeypatch
):
    enregistrer_secret(parametres.racine, "NEO4J_MEMORY_PASSWORD", "synthetic-private-memory-test")
    requests = []
    actual = httpx.AsyncClient

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"results": [{"data": []}], "errors": []})

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: actual(transport=httpx.MockTransport(handler), **kwargs),
    )
    memory = Memoire(parametres)
    query = "') DETACH DELETE n //"
    assert (await memory.chercher("client-a", query))["notes"] == []
    request = requests[0]
    assert str(request.url) == "http://127.0.0.1:47474/db/neo4j/tx/commit"
    statement = json.loads(request.content)["statements"][0]
    assert query not in statement["statement"]
    assert statement["parameters"] == {"scope": "client-a", "search": query}
    assert "LIMIT 100" in statement["statement"]


@pytest.mark.asyncio
async def test_no_note_or_link_can_escape_its_scope(parametres, monkeypatch):
    memory = Memoire(parametres)
    queries = []

    async def execute(query, parameters=None):
        queries.append((query, parameters))
        return []

    monkeypatch.setattr(memory, "requete", execute)
    with pytest.raises(HTTPException) as missing:
        await memory.obtenir("client-a", str(uuid4()))
    assert missing.value.status_code == 404
    with pytest.raises(HTTPException):
        await memory.lier(Lien(scope="client-a", origine=uuid4(), destination=uuid4()))
    assert "scope: $scope" in queries[-1][0]
    assert not any("MERGE" in query for query, _ in queries)
    assert queries[-1][1]["scope"] == "client-a"


@pytest.mark.asyncio
async def test_memory_relationship_cap_rejects_new_edges_but_allows_repeated_link(
    parametres, monkeypatch
):
    memory = Memoire(parametres)
    existing = False
    writes = []

    async def execute(query, parameters=None):
        if "AS degree" in query:
            return [
                {"degree": 30, "already": int(existing)},
                {"degree": 1, "already": int(existing)},
            ]
        writes.append(query)
        return [{"linked": True}]

    monkeypatch.setattr(memory, "requete", execute)
    link = Lien(scope="personal", origine=uuid4(), destination=uuid4())
    with pytest.raises(HTTPException) as quota:
        await memory.lier(link)
    assert quota.value.status_code == 409 and not writes
    existing = True
    assert await memory.lier(link) == {"linked": True}
    assert len(writes) == 1


@pytest.mark.asyncio
async def test_creation_initializes_constraints_and_caps_storage(parametres, monkeypatch):
    memory = Memoire(parametres)
    queries = []

    async def execute(query, parameters=None):
        queries.append((query, parameters))
        return []

    monkeypatch.setattr(memory, "requete", execute)
    with pytest.raises(HTTPException) as quota:
        await memory.creer(Note(scope="personal", titre="Test", contenu="Test", source="Fixture"))
    assert quota.value.status_code == 409
    assert "CREATE CONSTRAINT" in queries[0][0]
    assert "CREATE INDEX" in queries[1][0]
    assert "total < 5000" in queries[-1][0]
    assert not memory.verrou.locked()


def test_memory_snapshot_is_explicit_local_untrusted_and_does_not_copy_links(
    client, bearer, application, monkeypatch
):
    note_id = str(uuid4())

    async def get(scope, identifier):
        assert scope == "personal" and identifier == note_id
        return {
            "note": {
                "id": note_id,
                "maj_le": "2026-09-27",
                "titre": "Decision",
                "source": "Reviewed meeting notes",
                "contenu": "Synthetic context",
            },
            "liens": ["OTHER_NOTE_NOT_INCLUDED"],
        }

    monkeypatch.setattr(application.state.memoire, "obtenir", get)
    identifier = client.post("/api/conversations", headers=bearer, json={}).json()["id"]
    response = client.post(
        f"/api/conversations/{identifier}/memoire",
        headers=bearer,
        json={"scope": "personal", "identifiant": note_id},
    )
    assert response.status_code == 201
    from plateforme.conversations import Conversations

    context = Conversations(application.state.depot).contexte(
        identifier, "Explain", [response.json()["id"]]
    )
    assert "unverified context" in str(context) and "Synthetic context" in str(context)
    assert "OTHER_NOTE_NOT_INCLUDED" not in str(context)
