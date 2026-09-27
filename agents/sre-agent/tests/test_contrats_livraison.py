"""Delivery and observability contracts, independently of model quality."""

import hashlib
import json

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from test_graphe import DIAGNOSTIC, EXTRACTION, TRI, reponse, scenariser

from sre_agent import agent, cli, cli_graphe, config, graphe, outils, tracage
from sre_agent.budget import Budget
from sre_agent.modeles import Diagnostic, Rapport, appliquer_garde_source


@pytest.mark.parametrize(
    "source,action,expected",
    [
        ("read.md", "Vérifier le pool.", True),
        ("read.md", "Supprimer les données.", False),
        ("unread.md", "Vérifier le pool.", False),
        ("   ", "Vérifier le pool.", False),
    ],
)
def test_actions_require_a_passage_from_a_successful_read(source, action, expected):
    diagnosis = Diagnostic(
        cause_probable="test", confiance="faible", runbook_source=source, actions_proposees=[action]
    )
    retained, rejected = appliquer_garde_source(
        diagnosis, {"read.md": "# Diagnostic\nVérifier le pool."}
    )
    assert (action in retained.actions_proposees) is expected
    assert (action in rejected) is not expected


@pytest.mark.parametrize(
    "paragraph",
    [
        "Ne pas supprimer les données.",
        "Après confirmation du responsable, supprimer les données.",
    ],
)
def test_action_cannot_remove_negation_or_prerequisites(paragraph):
    diagnosis = Diagnostic(
        cause_probable="test",
        confiance="faible",
        runbook_source="read.md",
        actions_proposees=["supprimer les données."],
    )
    retained, rejected = appliquer_garde_source(diagnosis, {"read.md": paragraph})
    assert "supprimer les données." in rejected
    assert "supprimer les données." not in retained.actions_proposees


@pytest.mark.parametrize("alteration", ["digest", "truncated", "name", "error"])
def test_unverified_reads_never_create_provenance(alteration):
    content = "# Test\nVérifier le pool."
    envelope = {
        "fichier": "read.md",
        "texte": content,
        "tronque": False,
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
    }
    if alteration == "digest":
        envelope["sha256"] = "incorrect"
    if alteration == "truncated":
        envelope["tronque"] = True
    if alteration == "name":
        envelope["fichier"] = "another.md"
    result = "ERREUR OUTIL" if alteration == "error" else json.dumps(envelope)
    sources = {}
    outils._memoriser_source(result, {"nom": "read.md"}, sources)
    assert sources == {}


def test_pause_is_not_an_error_or_a_delivered_diagnosis(monkeypatch, tmp_path):
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(tracage, "tracer", lambda: provider.get_tracer("test"))
    scenariser(monkeypatch, [reponse(EXTRACTION), reponse(TRI), reponse(DIAGNOSTIC)])
    report = graphe.demarrer("synthetic", "pause", str(tmp_path / "db.sqlite"))
    assert report.statut == "en_attente_humain"
    assert report.diagnostic is None
    spans = exporter.get_finished_spans()
    gate = next(s for s in spans if s.name == "node.porte_humaine")
    assert gate.status.status_code is not StatusCode.ERROR
    assert not gate.events
    root = next(s for s in spans if s.name == "task.incident_analysis")
    assert tracage.ATTR_COUT not in root.attributes
    assert root.attributes[tracage.ATTR_COUT_TOTAL] == pytest.approx(0.03)
    assert all(tracage.ATTR_COUT not in s.attributes for s in spans if s.name.startswith("node."))
    provider.shutdown()


def test_legacy_checkpoint_cannot_deliver_an_unverified_diagnosis(monkeypatch, tmp_path):
    db = str(tmp_path / "legacy.sqlite")
    scenariser(monkeypatch, [reponse(EXTRACTION), reponse(TRI), reponse(DIAGNOSTIC)])
    assert graphe.demarrer("synthetic", "legacy", db).statut == "en_attente_humain"
    with graphe._application(db) as application:
        application.update_state(graphe._configuration("legacy"), {"version_contrat": 0})
    report = graphe.reprendre("oui", "legacy", db)
    assert report.statut == "erreur"
    assert "incompatible" in report.message
    assert report.diagnostic is None


@pytest.mark.parametrize(
    "decision,expected", [(True, True), (False, False), (1, False), (0, False), (None, False)]
)
def test_only_boolean_true_approves_structured_decisions(decision, expected):
    assert graphe._lire_decision({"approuve": decision})["approuve"] is expected


@pytest.mark.parametrize("alias", ["smart", "balanced", "fast"])
def test_sre_cannot_be_configured_for_external_reasoning(monkeypatch, alias):
    monkeypatch.setattr(config, "ALIAS_RAISONNEMENT", alias)
    assert agent.analyser("synthetic").statut == "erreur"


def test_oversized_alert_is_refused_before_any_work():
    assert agent.analyser("a" * (config.MAX_ALERTE + 1)).statut == "erreur"


def test_cli_returns_structured_error(monkeypatch, capsys):
    monkeypatch.delenv("CONFIDENTIAL_KEY", raising=False)
    assert cli.main(["synthetic", "--json"]) == 3
    assert json.loads(capsys.readouterr().out)["statut"] == "erreur"


def test_graph_cli_modes_are_exclusive():
    with pytest.raises(SystemExit) as result:
        cli_graphe.main(["--etat", "--reprendre", "oui", "--thread-id", "test"])
    assert result.value.code == 2


def test_resume_command_keeps_custom_database_path():
    report = Rapport(statut="en_attente_humain", message=json.dumps({"demande": "test"}))
    rendered = cli_graphe.rendre_graphe(report, "test", "/tmp/custom directory/db.sqlite")
    assert "--checkpoints '/tmp/custom directory/db.sqlite'" in rendered


def test_duration_budget_stops_before_network():
    budget = Budget(10, 1)
    budget.echeance = 0
    from sre_agent.budget import BudgetEpuise

    with pytest.raises(BudgetEpuise, match="durée"):
        budget.verifier_avant_llm()
