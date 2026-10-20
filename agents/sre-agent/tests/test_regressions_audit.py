"""Régressions de l'audit : données synthétiques et réseau intercepté."""

import json
import math

import httpx
import pytest
from test_graphe import DIAGNOSTIC, EXTRACTION, TRI, FauxClient, appel_outil, reponse, scenariser

from sre_agent import agent, cli_graphe, config, graphe, llm
from sre_agent.budget import Budget, BudgetEpuise
from sre_agent.modeles import Diagnostic, Extraction, appliquer_garde_source


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*a, **kw):
        pytest.fail("Appel réseau réel interdit dans les preuves hors ligne")

    monkeypatch.setattr(httpx, "post", forbidden)
    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setenv("CONFIDENTIAL_KEY", "audit-placeholder")
    monkeypatch.setenv("ORCHESTRATOR_KEY", "audit-placeholder")


@pytest.mark.parametrize("source", ["invented-runbook.md", "   "])
def test_source_must_be_verified(source):
    d = Diagnostic(
        cause_probable="synthetic",
        confiance="haute",
        actions_proposees=["ACTION_WITHOUT_EVIDENCE"],
        runbook_source=source,
    )
    result, _rejected = appliquer_garde_source(d)
    assert "ACTION_WITHOUT_EVIDENCE" not in result.actions_proposees


def test_failed_anonymisation_does_not_reach_frontier(monkeypatch):
    seen = []

    def capture(url, **kw):
        seen.append(kw["json"])
        return httpx.Response(200, json={"choices": [{"message": {"content": TRI}}]})

    monkeypatch.setattr(llm.httpx, "post", capture)
    extraction = Extraction(
        signature_technique="Erreur client AUDIT_CLIENT_42 à 192.0.2.42",
        requete_recherche="AUDIT_CLIENT_42",
    )
    agent._trier(extraction, Budget(10, 1))
    assert seen and all(payload["model"] == "local" for payload in seen)
    assert all(payload["reasoning_effort"] == "none" for payload in seen)


def test_missing_key_yields_error_report(monkeypatch):
    monkeypatch.delenv("CONFIDENTIAL_KEY")
    report = agent.analyser("alerte synthétique")
    assert report.statut == "erreur"


def test_invalid_gateway_json_yields_error_report(monkeypatch):
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: httpx.Response(200, text="not-json"))
    report = agent.analyser("alerte synthétique")
    assert report.statut == "erreur"


def test_non_finite_token_usage_yields_error_report(monkeypatch):
    body = '{"usage":{"prompt_tokens":1e999},"choices":[{"message":{"content":"{}"}}]}'
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: httpx.Response(200, text=body))
    assert agent.analyser("alerte synthétique").statut == "erreur"


def test_raw_error_body_not_exposed(monkeypatch):
    monkeypatch.setattr(
        llm.httpx,
        "post",
        lambda *a, **k: httpx.Response(502, text="AUDIT_SYNTHETIC_SENSITIVE_RESPONSE"),
    )
    report = agent.analyser("alerte synthétique")
    assert "AUDIT_SYNTHETIC_SENSITIVE_RESPONSE" not in report.message


@pytest.mark.parametrize("cost", ["NaN", "-1", "invalid", None])
def test_frontier_cost_must_be_known_and_valid(monkeypatch, cost):
    headers = {} if cost is None else {"x-litellm-response-cost": cost}
    monkeypatch.setattr(
        llm.httpx,
        "post",
        lambda *a, **k: httpx.Response(
            200, headers=headers, json={"choices": [{"message": {"content": "{}"}}]}
        ),
    )
    with pytest.raises((llm.ErreurPasserelle, ValueError, BudgetEpuise)):
        llm.appeler_llm(
            alias="smart",
            messages=[],
            classification=config.Classification.DERIVE,
            budget=Budget(10, 1),
            tache="audit",
        )


def test_nan_budget_is_invalid():
    with pytest.raises(ValueError):
        Budget(10, math.nan).verifier_avant_llm()


@pytest.mark.parametrize("value", ["false", "non", "0", [False]])
def test_structured_approval_requires_true_boolean(value):
    assert not graphe._lire_decision({"approuve": value})["approuve"]


def test_rejected_diagnosis_is_not_delivered(monkeypatch, tmp_path):
    db = str(tmp_path / "state.sqlite")
    scenariser(monkeypatch, [reponse(EXTRACTION), reponse(TRI), reponse(DIAGNOSTIC)])
    graphe.demarrer("synthetic", "audit-reject", db)
    report = graphe.reprendre("non", "audit-reject", db)
    assert report.statut == "rejete_par_humain"
    assert "Terminer les sessions idle" not in cli_graphe.rendre_graphe(report, "audit-reject", db)
    assert report.diagnostic is None


def test_final_answer_at_turn_limit_is_accepted(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MAX_TOURS", 1)
    scenariser(monkeypatch, [reponse(EXTRACTION), reponse(TRI), reponse(DIAGNOSTIC)])
    report = graphe.demarrer("synthetic", "audit-last-turn", str(tmp_path / "state.sqlite"))
    assert report.statut == "en_attente_humain"


def test_default_turn_budget_returns_report_not_recursion_error(monkeypatch, tmp_path):
    # MAX_TOURS=12 et MAX_APPELS_OUTILS=10, valeurs du dépôt.
    monkeypatch.setattr(config, "MAX_TOURS", 12)
    monkeypatch.setattr(config, "MAX_APPELS_OUTILS", 10)
    sequence = [reponse(EXTRACTION), reponse(TRI)]
    sequence += [reponse(appels_outils=[appel_outil("read_runbook", f"c{i}")]) for i in range(10)]
    sequence += [reponse("not JSON"), reponse(DIAGNOSTIC)]
    scenariser(monkeypatch, sequence)
    report = graphe.demarrer("synthetic", "audit-recursion", str(tmp_path / "state.sqlite"))
    assert report.statut in {"budget_epuise", "en_attente_humain"}


def test_raw_alert_is_not_persisted(monkeypatch, tmp_path):
    db = str(tmp_path / "state.sqlite")
    marker = "AUDIT_RAW_ALERT_SHOULD_STAY_IN_MEMORY"
    scenariser(monkeypatch, [reponse(EXTRACTION), reponse(TRI), reponse(DIAGNOSTIC)])
    graphe.demarrer(marker, "audit-storage", db)
    assert marker not in json.dumps(graphe.etat("audit-storage", db)["valeurs"], default=str)


def test_compiler_does_not_chmod_existing_parent_directory(tmp_path):
    parent = tmp_path / "shared"
    parent.mkdir(mode=0o755)
    # Set the fixture's intended permissions independently of the caller's umask.
    parent.chmod(0o755)
    graph = graphe.compiler(str(parent / "state.sqlite"))
    graph.checkpointer.conn.close()
    assert parent.stat().st_mode & 0o777 == 0o755


def test_tool_history_survives_budget_stop(monkeypatch):
    class FakeClient(FauxClient):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    client = FakeClient()
    monkeypatch.setattr(config, "MAX_APPELS_OUTILS", 1)
    monkeypatch.setattr(agent, "ClientRunbooks", lambda: client)
    sequence = iter(
        [
            reponse(EXTRACTION),
            reponse(TRI),
            reponse(
                appels_outils=[appel_outil("read_runbook", "c1"), appel_outil("read_runbook", "c2")]
            ),
        ]
    )
    monkeypatch.setattr(agent, "appeler_llm", lambda **kw: next(sequence))
    report = agent.analyser("synthetic")
    assert report.statut == "budget_epuise"
    assert report.budget["appels_outils"] == 1
    assert report.outils_appeles == ["read_runbook"]


def test_tool_timeout_yields_error_report(monkeypatch):
    class FakeClient(FauxClient):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def appeler(self, *a):
            raise TimeoutError("synthetic timeout")

    monkeypatch.setattr(agent, "ClientRunbooks", FakeClient)
    sequence = iter(
        [
            reponse(EXTRACTION),
            reponse(TRI),
            reponse(appels_outils=[appel_outil("read_runbook", "c1")]),
        ]
    )
    monkeypatch.setattr(agent, "appeler_llm", lambda **kw: next(sequence))
    report = agent.analyser("synthetic")
    assert report.statut == "erreur"


def test_unknown_checkpoint_type_is_not_reconstructed():
    from dataclasses import dataclass

    @dataclass
    class Unknown:
        value: str

    serializer = graphe._serialiseur()
    encoded = serializer.dumps_typed(Unknown("audit"))
    try:
        decoded = serializer.loads_typed(encoded)
    except (TypeError, ValueError):
        return
    assert not isinstance(decoded, Unknown)


def test_reused_thread_never_returns_previous_diagnosis(monkeypatch, tmp_path):
    db = str(tmp_path / "state.sqlite")
    scenariser(monkeypatch, [reponse(EXTRACTION), reponse(TRI), reponse(DIAGNOSTIC)])
    graphe.demarrer("first synthetic incident", "reused", db)
    graphe.reprendre("oui", "reused", db)
    scenariser(
        monkeypatch,
        [
            reponse(EXTRACTION),
            reponse(TRI),
            reponse("not JSON"),
            reponse(json.dumps({"cause_probable": "SECOND_DIAGNOSIS", "confiance": "faible"})),
        ],
    )
    report = graphe.demarrer("second distinct incident", "reused", db)
    assert report.statut == "erreur"
    assert report.diagnostic is None
    assert "existe déjà" in report.message


def test_approval_preview_contains_warnings(monkeypatch, tmp_path):
    db = str(tmp_path / "state.sqlite")
    ext = json.loads(EXTRACTION)
    ext["instructions_detectees"] = ["AUDIT_INJECTION_WARNING"]
    diag = json.loads(DIAGNOSTIC)
    diag["elements_manquants"] = ["AUDIT_MISSING_EVIDENCE"]
    scenariser(monkeypatch, [reponse(json.dumps(ext)), reponse(TRI), reponse(json.dumps(diag))])
    report = graphe.demarrer("synthetic", "preview", db)
    preview = cli_graphe.rendre_graphe(report, "preview", db)
    assert "AUDIT_MISSING_EVIDENCE" in preview
    assert "AUDIT_INJECTION_WARNING" in preview


def test_large_turn_limit_does_not_hit_framework_default(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MAX_TOURS", 30)
    monkeypatch.setattr(config, "MAX_APPELS_OUTILS", 30)
    monkeypatch.setattr(config, "MAX_COUT_USD", 10)
    seq = [reponse(EXTRACTION), reponse(TRI)]
    seq += [reponse(appels_outils=[appel_outil("read_runbook", f"c{i}")]) for i in range(26)]
    seq += [reponse(DIAGNOSTIC)]
    scenariser(monkeypatch, seq)
    report = graphe.demarrer("synthetic", "long", str(tmp_path / "long.sqlite"))
    assert report.statut == "en_attente_humain"
