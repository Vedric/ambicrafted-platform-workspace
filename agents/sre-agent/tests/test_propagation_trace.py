"""Propagation of the trace context to the gateway (ADR 0005).

Three properties, in order of importance:
1. With no active span, the call behaves exactly as before: no header
   added, no exception. That is the only case where the change could raise
   on a path that did not raise before.
2. With an active span, the traceparent header carries the trace_id and
   span_id of the current llm.* span, in W3C format.
3. The compartmentalisation guard stays ahead of header construction: a
   refusal reaches neither the injection nor the network.
"""

from __future__ import annotations

import re

import httpx
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from sre_agent import llm, tracage
from sre_agent.budget import Budget
from sre_agent.config import Classification

# Flags over two hex digits: sampled (bit 0) and, since level 2 of W3C
# Trace Context, random (bit 1). The SDK emits "03"; the gateway receives a
# valid header either way.
TRACEPARENT_W3C = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")


def _reponse_passerelle() -> httpx.Response:
    return httpx.Response(
        200,
        headers={"x-litellm-model-name": "ollama_chat/coder"},
        json={
            "model": "local",
            "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        },
    )


@pytest.fixture
def capture(monkeypatch):
    """Replace httpx.post; record the headers and the span current at call time."""
    monkeypatch.setenv("ORCHESTRATOR_KEY", "cle-de-test")
    monkeypatch.setenv("CONFIDENTIAL_KEY", "cle-de-test")
    vu: dict = {}

    def faux_post(_url, *, headers, **_k):
        vu["entetes"] = dict(headers)
        vu["contexte"] = trace.get_current_span().get_span_context()
        return _reponse_passerelle()

    monkeypatch.setattr(llm, "_poster_borne", faux_post)
    return vu


def _appel(alias: str = "local", classification=Classification.DERIVE) -> llm.ReponseLLM:
    return llm.appeler_llm(
        alias=alias,
        messages=[{"role": "user", "content": "bonjour"}],
        classification=classification,
        budget=Budget(max_appels_outils=1, max_cout_usd=1.0),
        tache="test",
    )


def test_sans_span_active_aucun_entete_et_aucune_exception(capture):
    """Tracing off (conftest: SRE_TRACAGE=0): the call is unchanged."""
    assert not tracage.tracer().start_span("sonde").get_span_context().is_valid, (
        "Le test suppose un traceur no-op ; le fournisseur de spans est installé."
    )

    resultat = _appel()

    assert resultat.contenu == "OK"
    assert not capture["contexte"].is_valid
    assert "traceparent" not in capture["entetes"]
    assert "tracestate" not in capture["entetes"]
    assert "baggage" not in capture["entetes"]
    assert set(capture["entetes"]) == {"Authorization", "Content-Type"}


def test_avec_span_active_le_traceparent_porte_la_span_llm(capture, monkeypatch):
    """The header is in W3C format and names the llm.* span as parent."""
    fournisseur = TracerProvider()  # real SDK, no exporter: nothing leaves
    monkeypatch.setattr(tracage, "tracer", lambda: fournisseur.get_tracer("test"))

    _appel()

    m = TRACEPARENT_W3C.match(capture["entetes"].get("traceparent", ""))
    assert m, f"traceparent absent ou mal formé : {capture['entetes']!r}"
    ctx = capture["contexte"]
    assert ctx.is_valid
    assert m.group(1) == format(ctx.trace_id, "032x")
    assert m.group(2) == format(ctx.span_id, "016x")
    assert int(m.group(3), 16) & 0x01, "bit sampled absent : la passerelle ne rattacherait pas"


def test_la_span_parente_est_transmise_a_la_passerelle(capture, monkeypatch):
    """The llm.* span is a child of the task span: same trace_id in the header."""
    fournisseur = TracerProvider()
    traceur = fournisseur.get_tracer("test")
    monkeypatch.setattr(tracage, "tracer", lambda: traceur)

    with traceur.start_as_current_span("task.incident_analysis") as parent:
        _appel()

    trace_id_parent = format(parent.get_span_context().trace_id, "032x")
    assert capture["entetes"]["traceparent"].split("-")[1] == trace_id_parent


@pytest.mark.parametrize("alias", ["smart", "balanced", "fast"])
def test_le_refus_precede_l_injection_et_le_reseau(alias, monkeypatch):
    """Barrier 1 comes first: neither inject nor httpx is reached."""
    monkeypatch.setenv("ORCHESTRATOR_KEY", "cle-de-test")

    def interdit(*_a, **_k):
        raise AssertionError("atteint malgré le refus")

    monkeypatch.setattr(llm.propagate, "inject", interdit)
    monkeypatch.setattr(llm, "_poster_borne", interdit)

    with pytest.raises(llm.FuiteConfidentielle):
        _appel(alias=alias, classification=Classification.CONFIDENTIEL)
