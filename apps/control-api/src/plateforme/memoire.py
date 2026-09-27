"""Explicit operator notes in the platform's dedicated Neo4j instance.

No arbitrary Cypher, remote URL, background ingestion or cross-scope traversal.
Stored notes are untrusted context, never verified runbook evidence.
"""

import asyncio
from typing import Literal
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from .config import Parametres, lire_environnement
from .depot import maintenant
from .services import json_borne

SCOPE = r"^[a-z0-9][a-z0-9_-]{0,63}$"


class Note(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    scope: str = Field(pattern=SCOPE)
    titre: str = Field(min_length=1, max_length=120)
    contenu: str = Field(min_length=1, max_length=4000)
    source: str = Field(min_length=1, max_length=500)
    type: Literal["fact", "decision", "question", "preference"] = "fact"


class Lien(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: str = Field(pattern=SCOPE)
    origine: UUID
    destination: UUID


class Memoire:
    def __init__(self, p: Parametres):
        self.p = p
        self.verrou = asyncio.Lock()
        self.initialisee = False

    async def requete(self, query: str, parameters: dict | None = None):
        password = lire_environnement(self.p.racine).get("NEO4J_MEMORY_PASSWORD", "")
        if not password:
            raise HTTPException(
                503,
                "Dedicated Neo4j memory is not configured. Follow the local memory setup guide.",
            )
        try:
            async with httpx.AsyncClient(
                timeout=15, trust_env=False, follow_redirects=False
            ) as client:
                result = await json_borne(
                    client,
                    "POST",
                    "http://127.0.0.1:47474/db/neo4j/tx/commit",
                    auth=httpx.BasicAuth("neo4j", password),
                    json={"statements": [{"statement": query, "parameters": parameters or {}}]},
                )
            if result.get("errors"):
                raise ValueError("Neo4j rejected the query")
            records = result["results"][0]["data"]
            if not isinstance(records, list) or len(records) > 101:
                raise ValueError("Graph response outside limits")
            return [row["row"][0] for row in records]
        except httpx.HTTPError, ValueError, KeyError, TypeError, IndexError:
            raise HTTPException(
                503, "Dedicated Neo4j memory is unavailable. Verify its health and credentials."
            ) from None

    async def initialiser(self):
        if self.initialisee:
            return
        await self.requete(
            "CREATE CONSTRAINT ambicrafted_note_id IF NOT EXISTS FOR (n:AmbicraftedNote) REQUIRE n.id IS UNIQUE"
        )
        await self.requete(
            "CREATE INDEX ambicrafted_note_scope IF NOT EXISTS FOR (n:AmbicraftedNote) ON (n.scope)"
        )
        self.initialisee = True

    async def statut(self):
        try:
            result = await self.requete("MATCH (n:AmbicraftedNote) RETURN {notes: count(n)}")
            return {"ready": True, "backend": "neo4j", "notes": result[0]["notes"], "local": True}
        except HTTPException:
            return {"ready": False, "backend": "neo4j", "notes": None, "local": True}

    async def chercher(self, scope: str, recherche: str = ""):
        notes = await self.requete(
            "MATCH (n:AmbicraftedNote {scope: $scope}) WHERE $search = '' OR toLower(n.titre + ' ' + n.contenu) CONTAINS toLower($search) RETURN properties(n) ORDER BY n.maj_le DESC, n.id LIMIT 100",
            {"scope": scope, "search": recherche},
        )
        return {"scope": scope, "notes": notes, "limit": 100, "verified": False}

    async def obtenir(self, scope: str, identifiant: str):
        rows = await self.requete(
            "MATCH (n:AmbicraftedNote {scope: $scope, id: $id}) OPTIONAL MATCH (n)-[:RELATED_TO]-(other:AmbicraftedNote {scope: $scope}) WITH n, collect(DISTINCT other.id)[..30] AS links RETURN {note: properties(n), liens: links}",
            {"scope": scope, "id": identifiant},
        )
        if not rows:
            raise HTTPException(404, "Memory note not found in this scope.")
        return {**rows[0], "verified": False}

    async def creer(self, note: Note):
        async with self.verrou:
            await self.initialiser()
            data = {
                **note.model_dump(),
                "id": str(uuid4()),
                "cree_le": maintenant(),
                "maj_le": maintenant(),
            }
            rows = await self.requete(
                "MATCH (existing:AmbicraftedNote) WITH count(existing) AS total WHERE total < 5000 CREATE (n:AmbicraftedNote) SET n = $note RETURN properties(n)",
                {"note": data},
            )
            if not rows:
                raise HTTPException(
                    409, "Memory limit reached. Delete unused notes before adding more."
                )
            return rows[0]

    async def lier(self, lien: Lien):
        if lien.origine == lien.destination:
            raise HTTPException(422, "Choose two distinct notes.")
        async with self.verrou:
            degrees = await self.requete(
                "MATCH (n:AmbicraftedNote {scope: $scope}) WHERE n.id IN [$from, $to] OPTIONAL MATCH (n)-[:RELATED_TO]-(other:AmbicraftedNote) WITH n, count(other) AS degree, count(CASE WHEN other.id IN [$from, $to] THEN 1 END) AS already RETURN {id: n.id, degree: degree, already: already}",
                {"scope": lien.scope, "from": str(lien.origine), "to": str(lien.destination)},
            )
            if len(degrees) != 2:
                raise HTTPException(404, "Both notes must belong to the selected scope.")
            if any(row["degree"] >= 30 and not row["already"] for row in degrees):
                raise HTTPException(409, "A note can have at most 30 relationships.")
            rows = await self.requete(
                "MATCH (a:AmbicraftedNote {scope: $scope, id: $from}), (b:AmbicraftedNote {scope: $scope, id: $to}) MERGE (a)-[:RELATED_TO]-(b) RETURN {linked: true}",
                {"scope": lien.scope, "from": str(lien.origine), "to": str(lien.destination)},
            )
            if not rows:
                raise HTTPException(404, "Both notes must belong to the selected scope.")
            return rows[0]

    async def supprimer(self, scope: str, identifiant: str):
        async with self.verrou:
            result = await self.requete(
                "MATCH (n:AmbicraftedNote {scope: $scope, id: $id}) DETACH DELETE n RETURN {deleted: true}",
                {"scope": scope, "id": identifiant},
            )
            if not result:
                raise HTTPException(404, "Memory note not found in this scope.")
            return result[0]


def routes(memory: Memoire, auth) -> APIRouter:
    router = APIRouter(prefix="/api/memoire")

    @router.get("/statut")
    async def statut(request: Request):
        auth.acteur(request)
        return await memory.statut()

    @router.get("")
    async def chercher(
        request: Request,
        scope: str = Query(pattern=SCOPE),
        recherche: str = Query("", max_length=200),
    ):
        auth.acteur(request)
        return await memory.chercher(scope, recherche)

    @router.get("/{identifiant}")
    async def obtenir(request: Request, identifiant: UUID, scope: str = Query(pattern=SCOPE)):
        auth.acteur(request)
        return await memory.obtenir(scope, str(identifiant))

    @router.post("", status_code=201)
    async def creer(request: Request, charge: Note):
        auth.acteur(request, mutation=True)
        auth.limiter("memoire", maximum=30)
        return await memory.creer(charge)

    @router.post("/liens")
    async def lier(request: Request, charge: Lien):
        auth.acteur(request, mutation=True)
        return await memory.lier(charge)

    @router.delete("/{identifiant}")
    async def supprimer(request: Request, identifiant: UUID, scope: str = Query(pattern=SCOPE)):
        auth.acteur(request, mutation=True)
        return await memory.supprimer(scope, str(identifiant))

    return router
