"""Authenticated history, document ingestion and streamed conversational replies."""

import asyncio
import hashlib
import json
import sqlite3
from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .assistant import flux_dialogue
from .conversations import Conversations
from .depot import Conflit, Introuvable
from .documents import extraire
from .memoire import SCOPE


class ReponseDialogue(StreamingResponse):
    """Own the inference lease even if sending headers fails before iteration starts."""

    def __init__(self, events, verrou):
        super().__init__(
            events, media_type="application/x-ndjson", headers={"X-Accel-Buffering": "no"}
        )
        self.events = events
        self.verrou = verrou

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            try:
                await self.events.aclose()
            finally:
                self.verrou.release()


class ChargeConversation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TitreConversation(ChargeConversation):
    titre: str = Field(default="New conversation", min_length=1, max_length=100)


class Piece(ChargeConversation):
    nom: str = Field(min_length=1, max_length=160)
    contenu: str = Field(min_length=1, max_length=11_184_812)


class Tour(ChargeConversation):
    message: str = Field(min_length=1, max_length=4000)
    operation_id: UUID
    langue: Literal["en", "fr"] = "en"
    pieces: list[UUID] = Field(default_factory=list, max_length=8)


class ContexteMemoire(ChargeConversation):
    scope: str = Field(pattern=SCOPE)
    identifiant: UUID


def routes(p, auth, moteur, depot, memoire) -> APIRouter:
    router = APIRouter(prefix="/api/conversations")
    store = Conversations(depot)
    store.purger()
    extraction = asyncio.Lock()

    @router.get("")
    async def lister(
        request: Request,
        recherche: str = Query("", max_length=100),
        page: int = Query(1, ge=1, le=10),
    ):
        auth.acteur(request)
        store.purger()
        return store.lister(recherche, page)

    @router.post("", status_code=201)
    async def creer(request: Request, charge: TitreConversation):
        auth.acteur(request, mutation=True)
        auth.limiter("conversations", maximum=30)
        return store.creer(charge.titre)

    @router.get("/{identifiant}")
    async def obtenir(request: Request, identifiant: UUID):
        auth.acteur(request)
        return store.obtenir(str(identifiant))

    @router.patch("/{identifiant}")
    async def renommer(request: Request, identifiant: UUID, charge: TitreConversation):
        auth.acteur(request, mutation=True)
        return store.renommer(str(identifiant), charge.titre)

    @router.delete("/{identifiant}")
    async def supprimer(request: Request, identifiant: UUID):
        auth.acteur(request, mutation=True)
        store.supprimer(str(identifiant))
        return {"supprime": True}

    @router.post("/{identifiant}/pieces", status_code=201)
    async def joindre(request: Request, identifiant: UUID, charge: Piece):
        auth.acteur(request, mutation=True)
        auth.limiter("pieces", maximum=12)
        store.obtenir(str(identifiant))
        if extraction.locked():
            raise HTTPException(409, "Another document is being processed. Try again shortly.")
        async with extraction:
            data = await extraire(charge.nom, charge.contenu)
            return store.ajouter_piece(str(identifiant), charge.nom, data)

    @router.delete("/{identifiant}/pieces/{piece_id}")
    async def retirer(request: Request, identifiant: UUID, piece_id: UUID):
        auth.acteur(request, mutation=True)
        store.retirer_piece(str(identifiant), str(piece_id))
        return {"supprime": True}

    @router.post("/{identifiant}/memoire", status_code=201)
    async def inclure_memoire(request: Request, identifiant: UUID, charge: ContexteMemoire):
        auth.acteur(request, mutation=True)
        auth.limiter("pieces", maximum=12)
        store.obtenir(str(identifiant))
        result = await memoire.obtenir(charge.scope, str(charge.identifiant))
        note = result["note"]
        snapshot = f"Operator memory — unverified context\nScope: {charge.scope}\nNote: {note['id']}\nUpdated: {note['maj_le']}\nTitle: {note['titre']}\nSource: {note['source']}\n{note['contenu']}"
        return store.ajouter_piece(
            str(identifiant),
            f"memory-{note['id']}.txt",
            {"kind": "text", "text": snapshot[:16000], "truncated": len(snapshot) > 16000},
        )

    @router.post("/{identifiant}/messages")
    async def envoyer(request: Request, identifiant: UUID, charge: Tour):
        auth.acteur(request, mutation=True)
        auth.limiter("dialogue", maximum=8)
        conversation_id, operation_id = str(identifiant), str(charge.operation_id)
        empreinte = hashlib.sha256(
            json.dumps(
                {
                    "message": charge.message,
                    "langue": charge.langue,
                    "pieces": sorted({str(value) for value in charge.pieces}),
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode()
        ).hexdigest()
        completed = store.deja_termine(conversation_id, operation_id, empreinte)
        if completed:

            async def cached():
                yield json.dumps({"type": "done", **completed}) + "\n"

            return StreamingResponse(cached(), media_type="application/x-ndjson")
        if moteur.inference.locked() or not moteur.file.empty():
            raise HTTPException(
                409, "The local engine is busy. Try again when the current task finishes."
            )
        messages = store.contexte(
            conversation_id, charge.message, [str(value) for value in charge.pieces]
        )
        # Acquired before headers, held until generation is complete or the browser disconnects.
        await moteur.inference.acquire()

        async def events():
            try:
                async for event in flux_dialogue(p, messages, charge.langue):
                    if event["type"] == "done":
                        store.enregistrer_tour(
                            conversation_id, operation_id, charge.message, event, empreinte
                        )
                    yield json.dumps(event, ensure_ascii=False) + "\n"
            except asyncio.CancelledError:
                raise
            except (
                httpx.HTTPError,
                ValueError,
                KeyError,
                IndexError,
                TypeError,
                AttributeError,
                TimeoutError,
                Conflit,
                Introuvable,
                sqlite3.Error,
            ):
                # No upstream body, source text, stack trace or credential reaches the client.
                yield (
                    json.dumps(
                        {
                            "type": "error",
                            "message": "The local reply was interrupted. Retry your message; partial replies are not saved.",
                        }
                    )
                    + "\n"
                )

        return ReponseDialogue(events(), moteur.inference)

    return router
