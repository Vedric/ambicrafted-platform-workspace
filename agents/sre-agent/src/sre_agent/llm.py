"""The single way through to the LiteLLM gateway.

Every LLM call the agent makes goes through `appeler_llm`. That is what
makes the compartmentalisation verifiable: there is one place to read to
know whether customer data can leave, and one place to change for that to
stop being true. A direct httpx call elsewhere in the package would be an
architectural defect, not an optimisation.

Three barriers, in this order:
1. Application guard: classification CONFIDENTIEL + a frontier alias
   raises FuiteConfidentielle before any network access.
2. Virtual key: a confidential payload is sent with CONFIDENTIAL_KEY,
   restricted gateway-side to local and local-embed.
3. Gateway: no fallback is configured from `local`, so a local failure
   has no path back to the frontier.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx
from opentelemetry import propagate
from opentelemetry.trace import SpanKind, Status, StatusCode

from . import config, tracage
from .budget import Budget
from .config import ALIAS_CONNUS, ALIAS_LOCAUX, Classification


class FuiteConfidentielle(RuntimeError):
    """A confidential call targeted a frontier alias. Nothing was sent."""


class ErreurPasserelle(RuntimeError):
    """The gateway refused, or did not answer."""


@dataclass
class ReponseLLM:
    contenu: str
    appels_outils: list[dict[str, Any]] = field(default_factory=list)
    message: dict[str, Any] = field(default_factory=dict)
    cout_usd: float = 0.0
    tokens_entree: int = 0
    tokens_sortie: int = 0
    motif_arret: str = ""


def _cout_depuis_entetes(entetes: httpx.Headers) -> float:
    """Read the cost the gateway reports.

    The gateway is the authority on price: the agent keeps no rate table,
    which would in any case require it to know a model name. The flat
    header is absent when the cost is zero.
    """
    for nom in ("x-litellm-response-cost", "x-litellm-response-cost-original"):
        brut = entetes.get(nom)
        if brut:
            try:
                return float(brut)
            except ValueError:
                continue
    return 0.0


def _systeme_depuis_entetes(entetes: httpx.Headers) -> str:
    """Derive gen_ai.system from what the gateway reports having served.

    A value read at run time, never written in the code: rule 1 of
    CLAUDE.md forbids writing a provider name into the source, not
    observing the one the gateway picked.
    """
    nom = entetes.get("x-litellm-model-name", "")
    return nom.split("/", 1)[0] if "/" in nom else (nom or "inconnu")


def appeler_llm(
    *,
    alias: str,
    messages: list[dict[str, Any]],
    classification: Classification,
    budget: Budget,
    tache: str,
    outils: list[dict[str, Any]] | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.0,
    format_json: bool = False,
) -> ReponseLLM:
    """Call a model by its alias, under the compartmentalisation guard.

    Args:
        alias: a gateway alias. Never a provider model name.
        classification: the nature of the data `messages` carries.
        budget: the run's counters, updated here.
        tache: the value of ambicrafted.task.type on the span.
    """
    if alias not in ALIAS_CONNUS:
        raise ErreurPasserelle(
            f"Alias inconnu : {alias!r}. Alias déclarés : {sorted(ALIAS_CONNUS)}."
        )

    # --- Barrier 1: application guard, before any network access --------
    if classification is Classification.CONFIDENTIEL and alias not in ALIAS_LOCAUX:
        raise FuiteConfidentielle(
            f"Refus : charge classée {classification.value} vers l'alias frontière "
            f"{alias!r}. Une donnée d'alerte brute ne quitte pas la machine. "
            f"Alias autorisés pour cette classification : {sorted(ALIAS_LOCAUX)}."
        )

    budget.verifier_avant_llm()

    corps: dict[str, Any] = {
        "model": alias,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if outils:
        corps["tools"] = outils
        corps["tool_choice"] = "auto"
    if format_json:
        corps["response_format"] = {"type": "json_object"}

    with tracage.tracer().start_as_current_span(
        f"llm.{tache}", kind=SpanKind.CLIENT
    ) as span:
        span.set_attribute(tracage.ATTR_CLASSIFICATION, classification.value)
        span.set_attribute(tracage.ATTR_TYPE_TACHE, tache)
        span.set_attribute(tracage.ATTR_ALIAS, alias)
        span.set_attribute("gen_ai.operation.name", "chat")
        span.set_attribute("gen_ai.request.model", alias)
        span.set_attribute("gen_ai.request.max_tokens", max_tokens)
        span.set_attribute("gen_ai.request.temperature", temperature)

        entetes = {
            # --- Barrier 2: restricted key for confidential payloads
            "Authorization": f"Bearer {config.cle(classification)}",
            "Content-Type": "application/json",
        }
        # W3C trace context (traceparent): the gateway hangs its own spans
        # under this llm.* span, and an LLM call stops being two disjoint
        # traces (ADR 0005). Injected here, so after barrier 1: a refused
        # payload never gets a header built for it at all. With no active
        # span (tracing off), the propagator writes nothing.
        propagate.inject(entetes)

        try:
            reponse = httpx.post(
                f"{config.LITELLM_BASE_URL.rstrip('/')}/chat/completions",
                headers=entetes,
                json=corps,
                timeout=config.TIMEOUT_LLM_S,
            )
        except httpx.HTTPError as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise ErreurPasserelle(
                f"Passerelle injoignable sur {config.LITELLM_BASE_URL} : "
                f"{type(e).__name__} : {e}"
            ) from e

        cout = _cout_depuis_entetes(reponse.headers)
        span.set_attribute("gen_ai.system", _systeme_depuis_entetes(reponse.headers))
        span.set_attribute(tracage.ATTR_COUT, cout)

        if reponse.status_code != 200:
            span.set_status(Status(StatusCode.ERROR, f"HTTP {reponse.status_code}"))
            raise ErreurPasserelle(
                f"Passerelle : HTTP {reponse.status_code} sur l'alias {alias!r}. "
                f"{reponse.text[:400]}"
            )

        donnees = reponse.json()
        usage = donnees.get("usage") or {}
        entree = int(usage.get("prompt_tokens") or 0)
        sortie = int(usage.get("completion_tokens") or 0)

        choix = (donnees.get("choices") or [{}])[0]
        message = choix.get("message") or {}

        span.set_attribute("gen_ai.response.model", str(donnees.get("model", alias)))
        span.set_attribute("gen_ai.usage.input_tokens", entree)
        span.set_attribute("gen_ai.usage.output_tokens", sortie)
        span.set_attribute(
            "gen_ai.response.finish_reasons", [str(choix.get("finish_reason", ""))]
        )

        resultat = ReponseLLM(
            contenu=message.get("content") or "",
            appels_outils=list(message.get("tool_calls") or []),
            message=message,
            cout_usd=cout,
            tokens_entree=entree,
            tokens_sortie=sortie,
            motif_arret=str(choix.get("finish_reason") or ""),
        )
        span.set_attribute("gen_ai.response.tool_calls", len(resultat.appels_outils))

        # Charged inside the span: an overrun stays visible in the trace.
        budget.consommer_llm(cout, entree, sortie)
        span.set_attribute("ambicrafted.budget.spent_usd", round(budget.cout_usd, 6))

    return resultat


_BLOC_JSON = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extraire_json(texte: str) -> dict[str, Any]:
    """Extract a JSON object from a model response.

    Reasoning models happily wrap their JSON in prose or Markdown fences.
    Rather than demanding clean output through the prompt, which is never
    guaranteed, we accept the three shapes actually seen and fail clearly
    when none of them applies.
    """
    candidats: list[str] = []
    if m := _BLOC_JSON.search(texte):
        candidats.append(m.group(1))
    debut, fin = texte.find("{"), texte.rfind("}")
    if debut != -1 and fin > debut:
        candidats.append(texte[debut : fin + 1])
    candidats.append(texte)

    for candidat in candidats:
        try:
            valeur = json.loads(candidat.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(valeur, dict):
            return valeur

    raise ErreurPasserelle(
        f"Réponse du modèle non exploitable comme JSON : {texte[:300]!r}"
    )
