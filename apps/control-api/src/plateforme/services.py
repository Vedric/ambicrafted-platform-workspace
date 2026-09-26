"""Bounded read-only probes and typed responses from fixed local destinations."""

import asyncio
import json
import time
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import Parametres, lire_environnement

SERVICES = [
    (
        "litellm",
        "Passerelle IA",
        "http://127.0.0.1:4000/health/liveliness",
        "http://localhost:4000/ui",
    ),
    ("ollama", "Inférence locale", "http://172.17.0.1:11434/api/tags", None),
    (
        "qdrant",
        "Mémoire vectorielle",
        "http://127.0.0.1:6333/collections",
        "http://localhost:6333/dashboard",
    ),
    ("prometheus", "Métriques", "http://127.0.0.1:9090/-/ready", "http://localhost:9090"),
    ("tempo", "Traces", "http://127.0.0.1:3200/ready", None),
    (
        "grafana",
        "Observabilité",
        "http://127.0.0.1:3000/api/health",
        "http://localhost:3000/d/plateforme-sre",
    ),
]
MAX_REPONSE = 1_000_000
DIMENSION = 768  # Must match the versioned runbook index contract.


class DonneesLocales(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True, allow_inf_nan=False)


class ModeleLocal(DonneesLocales):
    name: str = Field(min_length=1, max_length=256)
    size: int = Field(default=0, ge=0, le=10**15)


class ReponseModeles(DonneesLocales):
    models: list[ModeleLocal] = Field(default_factory=list, max_length=1000)


class IndexLocal(DonneesLocales):
    points_count: int = Field(ge=0)
    status: Literal["green", "yellow", "grey", "red"]


class ReponseIndex(DonneesLocales):
    result: IndexLocal


class EtiquettesCible(DonneesLocales):
    job: str = Field(default="cible", min_length=1, max_length=256)


class CibleLocale(DonneesLocales):
    labels: EtiquettesCible = Field(default_factory=EtiquettesCible)
    health: Literal["up", "down", "unknown"]
    lastScrape: str = Field(default="", max_length=100)
    lastScrapeDuration: float = Field(default=0, ge=0)


class ListeCibles(DonneesLocales):
    activeTargets: list[CibleLocale] = Field(default_factory=list, max_length=1000)


class ReponseCibles(DonneesLocales):
    data: ListeCibles


class VecteurLocal(DonneesLocales):
    embedding: list[float] = Field(min_length=DIMENSION, max_length=DIMENSION)
    index: int = Field(default=0, ge=0, le=0)

    @field_validator("embedding")
    @classmethod
    def non_nul(cls, valeur: list[float]) -> list[float]:
        if not any(valeur):
            raise ValueError("Vecteur nul refusé.")
        return valeur


class ReponseVecteur(DonneesLocales):
    data: list[VecteurLocal] = Field(min_length=1, max_length=1)


class PassageLocal(DonneesLocales):
    fichier: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,115}\.md$")
    chemin_titres: str = Field(default="", max_length=8000)
    texte: str = Field(default="", max_length=8000)
    ligne_debut: int | None = Field(default=None, ge=1)
    corpus_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class PointLocal(DonneesLocales):
    score: float
    payload: PassageLocal


class ListePoints(DonneesLocales):
    points: list[PointLocal] = Field(max_length=5)


class ReponseRecherche(DonneesLocales):
    result: ListePoints


async def json_borne(client: httpx.AsyncClient, methode: str, url: str, **options: Any) -> Any:
    """Reject large responses before JSON parsing, including chunked responses."""
    async with client.stream(methode, url, **options) as reponse:
        reponse.raise_for_status()
        if int(reponse.headers.get("content-length", "0")) > MAX_REPONSE:
            raise ValueError("Réponse locale trop volumineuse.")
        corps = bytearray()
        async for bloc in reponse.aiter_bytes(chunk_size=8192):
            corps.extend(bloc)
            if len(corps) > MAX_REPONSE:
                raise ValueError("Réponse locale trop volumineuse.")
        return json.loads(corps)


class Services:
    def __init__(self, p: Parametres):
        self.p = p
        self.cache: dict = {}
        self.date = 0.0
        self.verrou = asyncio.Lock()

    async def sante(self) -> dict:
        async with self.verrou:
            if time.monotonic() - self.date < 10 and self.cache:
                return self.cache
            async with httpx.AsyncClient(
                timeout=3, trust_env=False, follow_redirects=False
            ) as client:

                async def sonder(service):
                    identifiant, nom, url, lien = service
                    debut = time.monotonic()
                    try:
                        # Liveness needs the HTTP status, not an unbounded response body.
                        async with client.stream("GET", url) as reponse:
                            ok = reponse.status_code == 200
                    except httpx.HTTPError:
                        ok = False
                    return {
                        "id": identifiant,
                        "nom": nom,
                        "ok": ok,
                        "latence_ms": round((time.monotonic() - debut) * 1000),
                        "lien": lien,
                    }

                services = await asyncio.gather(*(sonder(s) for s in SERVICES))
                modeles, index = [], {}
                try:
                    async with asyncio.timeout(5):
                        donnees = ReponseModeles.model_validate(
                            await json_borne(client, "GET", "http://172.17.0.1:11434/api/tags")
                        )
                    modeles = [{"nom": m.name, "taille": m.size} for m in donnees.models[:20]]
                except httpx.HTTPError, ValueError, TimeoutError:
                    pass
                try:
                    async with asyncio.timeout(5):
                        resultat = ReponseIndex.model_validate(
                            await json_borne(
                                client, "GET", "http://127.0.0.1:6333/collections/runbooks-current"
                            )
                        ).result
                    index = {"points": resultat.points_count, "statut": resultat.status}
                except httpx.HTTPError, ValueError, TimeoutError:
                    pass
            self.cache = {
                "services": services,
                "modeles": modeles,
                "index": index,
                "ok": all(s["ok"] for s in services),
            }
            self.date = time.monotonic()
            return self.cache

    async def cibles(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=4, trust_env=False, follow_redirects=False) as client:
            try:
                async with asyncio.timeout(5):
                    resultat = ReponseCibles.model_validate(
                        await json_borne(client, "GET", "http://127.0.0.1:9090/api/v1/targets")
                    )
                return [
                    {
                        "nom": t.labels.job,
                        "sante": t.health,
                        "dernier_scrape": t.lastScrape,
                        "duree_s": t.lastScrapeDuration,
                    }
                    for t in resultat.data.activeTargets[:40]
                ]
            except httpx.HTTPError, ValueError, TimeoutError:
                return []

    async def semantique(self, requete: str) -> list[dict]:
        valeurs = lire_environnement(self.p.racine)
        cle = valeurs.get("CONFIDENTIAL_KEY", "")
        if not cle:
            raise ValueError("La clé confidentielle locale est nécessaire.")
        async with (
            asyncio.timeout(35),
            httpx.AsyncClient(timeout=30, trust_env=False, follow_redirects=False) as client,
        ):
            reponse = ReponseVecteur.model_validate(
                await json_borne(
                    client,
                    "POST",
                    "http://127.0.0.1:4000/v1/embeddings",
                    headers={"Authorization": "Bearer " + cle},
                    json={"model": "local-embed", "input": "search_query: " + requete},
                )
            )
            vecteur = reponse.data[0].embedding
            resultat = ReponseRecherche.model_validate(
                await json_borne(
                    client,
                    "POST",
                    "http://127.0.0.1:6333/collections/runbooks-current/points/query",
                    json={"query": vecteur, "limit": 5, "with_payload": True},
                )
            )
            return [
                {"score": p.score, "donnees": p.payload.model_dump(exclude_none=True)}
                for p in resultat.result.points
            ]
