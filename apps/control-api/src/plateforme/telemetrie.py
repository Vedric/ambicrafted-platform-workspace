"""Authenticated numeric browser observations, never browsing or customer content."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

Route = Literal[
    "workspace",
    "assistant",
    "analyses",
    "knowledge",
    "memory",
    "architecture",
    "observability",
    "settings",
    "guide",
    "other",
]


class Echantillon(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    metric: Literal["LCP", "INP", "CLS"]
    route: Route
    value: float = Field(ge=0, le=300_000)

    @model_validator(mode="after")
    def borne_cls(self):
        if self.metric == "CLS" and self.value > 100:
            raise ValueError("CLS outside bounds")
        return self


class Navigation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    samples: list[Echantillon] = Field(min_length=1, max_length=12)


def routes(auth, mesures):
    router = APIRouter(prefix="/api/telemetrie")

    @router.post("/navigation", status_code=204)
    async def navigation(request: Request, charge: Navigation):
        if auth.acteur(request, mutation=True) != "operateur":
            raise HTTPException(403, "Session navigateur requise.")
        auth.limiter("telemetrie", maximum=30)
        for sample in charge.samples:
            if sample.metric == "CLS":
                mesures.layout_shift.labels(sample.route).observe(sample.value)
            else:
                mesures.web_vitals.labels(sample.metric, sample.route).observe(sample.value / 1000)
        return Response(status_code=204)

    return router
