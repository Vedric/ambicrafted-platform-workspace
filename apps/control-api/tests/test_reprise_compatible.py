"""Legacy decisions fail before mutating durable history or the in-memory queue."""

import json
import uuid

import pytest
from sre_agent.graphe import VERSION_CONTRAT

from plateforme.depot import Conflit


@pytest.mark.parametrize("marker", [None, 2, "3", 3.0, True, 4])
@pytest.mark.parametrize("decision", [True, False])
def test_legacy_api_decision_preserves_history_checkpoint_and_queue(
    client, application, bearer, marker, decision
):
    identifier = uuid.uuid4().hex
    options = {} if marker is None else {"version_contrat": marker}
    store, engine = application.state.depot, application.state.moteur
    store.creer(identifier, "Synthetic legacy pause", "graphe", options, "test")
    store.changer(
        identifier,
        "en_attente_humain",
        rapport={"statut": "en_attente_humain", "message": "Original pending report"},
    )
    directory = engine.racine / identifier
    directory.mkdir(mode=0o700)
    checkpoint = directory / "graphe.sqlite"
    checkpoint.write_bytes(b"Synthetic untouched checkpoint boundary")
    before, journal = store.obtenir(identifier), store.journal()
    assert before["reprise_compatible"] is False
    listed = client.get("/api/analyses", headers=bearer).json()["elements"]
    assert listed[0]["reprise_compatible"] is False
    assert client.get(f"/api/analyses/{identifier}", headers=bearer).json() == before
    response = client.post(
        f"/api/analyses/{identifier}/decision",
        headers=bearer,
        json={"approuver": decision},
    )
    assert response.status_code == 409
    assert "Historique conservé" in response.json()["detail"]
    assert store.obtenir(identifier) == before
    assert store.journal() == journal
    assert engine.file.empty() and not engine.alertes and not engine.processus
    assert checkpoint.read_bytes() == b"Synthetic untouched checkpoint boundary"


def test_engine_persists_current_marker_without_persisting_raw_alert(moteur):
    alert = "Synthetic original input must stay in memory"
    analysis = moteur.creer("Current contract", alert, "test")
    assert analysis["options"] == {"version_contrat": VERSION_CONTRAT}
    assert analysis["reprise_compatible"] is True
    assert alert not in json.dumps(moteur.depot.obtenir(analysis["id"]))
    operation = moteur.creer("Check services", "", "test", operation="verifier")
    assert operation["options"] == {"operation": "verifier"}
    assert operation["reprise_compatible"] is False


def test_engine_legacy_guard_precedes_even_full_queue(moteur):
    legacy = uuid.uuid4().hex
    moteur.depot.creer(legacy, "Legacy", "graphe", {}, "test")
    moteur.depot.changer(legacy, "en_attente_humain")
    for _ in range(moteur.p.taille_file):
        moteur.creer("Queued synthetic", "Synthetic", "test")
    before = moteur.depot.obtenir(legacy)
    journal, size = moteur.depot.journal(), moteur.file.qsize()
    with pytest.raises(Conflit, match="ancien contrat"):
        moteur.decider(legacy, True, "test")
    assert moteur.depot.obtenir(legacy) == before
    assert moteur.depot.journal() == journal and moteur.file.qsize() == size


@pytest.mark.parametrize(
    "extra", [{"options": {"version_contrat": 3}}, {"reprise_compatible": True}]
)
def test_client_cannot_choose_contract_or_resume_capability(client, application, bearer, extra):
    response = client.post(
        "/api/analyses",
        headers=bearer,
        json={"titre": "Synthetic", "alerte": "Synthetic", **extra},
    )
    assert response.status_code == 422
    assert application.state.depot.lister()["total"] == 0
    assert application.state.moteur.file.empty()
