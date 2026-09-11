"""Tests of the LangGraph port, on an unplugged machine.

Same requirement as `test_gardefous.py`: no gateway, no MCP server, no
network. What is checked here is not the framework: it is that the port
loosened nothing, and that the new properties (edge routing, durable
pause) actually hold.

The substitution points are `appeler_llm` and the tool client. Everything
else (budget, allowlist, containment, source guard) is the production
code, run as is.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from sre_agent import cli_graphe, config, graphe, llm, outils
from sre_agent.budget import Budget
from sre_agent.config import Classification
from sre_agent.llm import ReponseLLM

# --- Test doubles ----------------------------------------------------------


class FauxClient:
    """A tool server that answers, and counts what it is asked for."""

    def __init__(self, reponse: str = "## Runbook\nTerminer les sessions idle.") -> None:
        self.reponse = reponse
        self.appels: list[str] = []

    def outils_openai(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {"name": "semantic_search", "description": "", "parameters": {}},
            }
        ]

    def appeler(self, nom: str, arguments: dict) -> str:
        self.appels.append(nom)
        return self.reponse


def reponse(contenu: str = "", appels_outils=None, cout: float = 0.01) -> ReponseLLM:
    message: dict = {"role": "assistant"}
    if contenu:
        message["content"] = contenu
    if appels_outils:
        message["tool_calls"] = appels_outils
    return ReponseLLM(
        contenu=contenu,
        appels_outils=list(appels_outils or []),
        message=message,
        cout_usd=cout,
        tokens_entree=10,
        tokens_sortie=10,
    )


def appel_outil(nom: str, identifiant: str) -> dict:
    return {"id": identifiant, "function": {"name": nom, "arguments": "{}"}}


EXTRACTION = json.dumps(
    {
        "signature_technique": "PostgreSQL: too many clients already",
        "symptomes": ["connexions refusées"],
        "composants": ["base de données relationnelle"],
        "requete_recherche": "saturation du pool de connexions",
        "identifiants_retires": ["nom d'hôte"],
        "instructions_detectees": [],
    }
)
TRI = json.dumps(
    {"connue": True, "urgence": 4, "actionnable": True, "justification": "motif connu"}
)
DIAGNOSTIC = json.dumps(
    {
        "cause_probable": "Saturation du pool de connexions.",
        "confiance": "haute",
        "elements_manquants": [],
        "actions_proposees": ["Terminer les sessions idle"],
        "runbook_source": "incident-p1-database.md",
    }
)


def scenariser(monkeypatch, suite: list[ReponseLLM], client: FauxClient | None = None):
    """Install a sequence of LLM responses and a fake tool client.

    The budget stays the real one: the double charges it as the gateway
    would, which leaves the ceilings fully enforceable.
    """
    restant = list(suite)

    def faux_appel(*, budget: Budget, **_kwargs) -> ReponseLLM:
        budget.verifier_avant_llm()
        if not restant:
            raise AssertionError("Plus de réponse scénarisée : le graphe boucle.")
        r = restant.pop(0)
        budget.consommer_llm(r.cout_usd, r.tokens_entree, r.tokens_sortie)
        return r

    monkeypatch.setattr(graphe, "appeler_llm", faux_appel)
    monkeypatch.setattr(graphe, "_client", lambda: client or FauxClient())
    return restant


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "graphe.sqlite")


# --- The human gate, and the survival of the state ------------------------


def test_le_graphe_s_arrete_avant_de_livrer(monkeypatch, db):
    """Nothing is delivered until a human has seen the diagnosis."""
    scenariser(
        monkeypatch,
        [
            reponse(EXTRACTION),
            reponse(TRI),
            reponse(appels_outils=[appel_outil("semantic_search", "c1")]),
            reponse(DIAGNOSTIC),
        ],
    )
    rapport = graphe.demarrer("PostgreSQL: too many clients already", "t-porte", db)

    assert rapport.statut == "en_attente_humain"
    # The diagnosis is SUBMITTED, not delivered: the approval request
    # carries it, and the state holds no trace of a human decision.
    demande = json.loads(rapport.message)
    assert demande["runbook_source"] == "incident-p1-database.md"
    assert demande["actions_proposees"] == ["Terminer les sessions idle"]

    instantane = graphe.etat("t-porte", db)
    assert instantane["prochains_noeuds"] == ["porte_humaine"]
    assert instantane["valeurs"].get("approbation") is None
    assert instantane["valeurs"].get("statut") == "en_cours"
    assert instantane["en_attente"]  # the checkpoint knows it is waiting


def test_la_reprise_repart_du_meme_point(monkeypatch, db):
    """A recompiled application, with no LLM response left, still completes.

    That is the proof the context comes from the checkpoint and not from
    memory: the scripted sequence is empty by the time of the resume, so
    no model call is possible.
    """
    scenariser(
        monkeypatch,
        [reponse(EXTRACTION), reponse(TRI), reponse(DIAGNOSTIC)],
    )
    graphe.demarrer("PostgreSQL: too many clients already", "t-reprise", db)

    # Not a single response left: everything has to come from SQLite.
    scenariser(monkeypatch, [])
    rapport = graphe.reprendre("oui", "t-reprise", db)

    assert rapport.statut == "complet"
    assert rapport.diagnostic is not None
    assert rapport.diagnostic.runbook_source == "incident-p1-database.md"
    assert rapport.diagnostic.actions_proposees == ["Terminer les sessions idle"]


def test_un_refus_ne_livre_rien(monkeypatch, db):
    scenariser(monkeypatch, [reponse(EXTRACTION), reponse(TRI), reponse(DIAGNOSTIC)])
    graphe.demarrer("alerte", "t-refus", db)
    scenariser(monkeypatch, [])
    rapport = graphe.reprendre("non, je veux vérifier la volumétrie", "t-refus", db)

    assert rapport.statut == "rejete_par_humain"
    assert "Refus ou réserve" in rapport.message


def test_le_silence_ne_vaut_pas_approbation(monkeypatch, db):
    """A permissive default would turn the gate into a formality."""
    scenariser(monkeypatch, [reponse(EXTRACTION), reponse(TRI), reponse(DIAGNOSTIC)])
    graphe.demarrer("alerte", "t-vide", db)
    scenariser(monkeypatch, [])
    assert graphe.reprendre("", "t-vide", db).statut == "rejete_par_humain"


# --- Budgets enforced by an edge, not by an exception ---------------------


def test_budget_outils_route_vers_abandon(monkeypatch, db):
    """Ceiling at 2: the burst of 3 tools is refused, with no exception."""
    monkeypatch.setattr(config, "MAX_APPELS_OUTILS", 2)
    client = FauxClient()
    scenariser(
        monkeypatch,
        [
            reponse(EXTRACTION),
            reponse(TRI),
            reponse(
                appels_outils=[
                    appel_outil("semantic_search", "c1"),
                    appel_outil("read_runbook", "c2"),
                    appel_outil("search_runbooks", "c3"),
                ]
            ),
        ],
        client,
    )
    rapport = graphe.demarrer("alerte", "t-budget", db)

    assert rapport.statut == "budget_epuise"
    assert rapport.diagnostic is None
    # The reason names the right ceiling: "tools" and "turns" call for
    # opposite fixes, and confusing them costs on-call time.
    assert "plafond d'appels d'outils atteint" in rapport.message
    assert "salve de 3 outil(s)" in rapport.message
    assert "tours" not in rapport.message
    # No tool ran: the edge decided before the node.
    assert client.appels == []


def test_budget_monetaire_route_vers_abandon(monkeypatch, db):
    monkeypatch.setattr(config, "MAX_COUT_USD", 0.02)
    scenariser(
        monkeypatch,
        [reponse(EXTRACTION, cout=0.015), reponse(TRI, cout=0.010)],
    )
    rapport = graphe.demarrer("alerte", "t-cout", db)

    assert rapport.statut == "budget_epuise"
    assert rapport.diagnostic is None
    assert rapport.budget["cout_usd"] == pytest.approx(0.025)
    # Message emitted by budget.py itself: the guardrail raised inside the
    # node, the edge only had to route. The reconstruction serves only the
    # refusals pronounced by the edge before the node is even entered.
    assert "plafond monétaire dépassé" in rapport.message


def test_plafond_de_tours_route_vers_abandon(monkeypatch, db):
    monkeypatch.setattr(config, "MAX_TOURS", 2)
    client = FauxClient()
    scenariser(
        monkeypatch,
        [
            reponse(EXTRACTION),
            reponse(TRI),
            reponse(appels_outils=[appel_outil("semantic_search", "c1")]),
            reponse(appels_outils=[appel_outil("read_runbook", "c2")]),
        ],
        client,
    )
    rapport = graphe.demarrer("alerte", "t-tours", db)

    assert rapport.statut == "budget_epuise"
    assert "plafond de tours de boucle atteint" in rapport.message


# --- Compartmentalisation survives the port -------------------------------


def test_charge_confidentielle_refusee_dans_le_graphe(monkeypatch, db):
    """The extraction node stays subject to the guard in `llm.py`.

    No double here: the real `appeler_llm` runs, and the network is
    trapped to prove it is never reached.
    """

    def interdit(*_a, **_k):
        raise AssertionError("Un appel réseau a été tenté malgré le refus.")

    monkeypatch.setattr(llm.httpx, "post", interdit)
    monkeypatch.setattr(config, "ALIAS_EXTRACTION", "smart")
    monkeypatch.setattr(graphe, "_client", lambda: FauxClient())

    rapport = graphe.demarrer("alerte client avec un nom d'hôte", "t-fuite", db)

    assert rapport.statut == "erreur"
    assert rapport.message.startswith("FuiteConfidentielle")
    assert "ne quitte pas la machine" in rapport.message
    assert rapport.diagnostic is None


def test_la_classification_du_noeud_extraction_est_confidentielle(monkeypatch, db):
    """The classification is passed by the node, not inferred from the graph."""
    vues: list[Classification] = []

    def espion(*, classification, budget, **_k):
        vues.append(classification)
        budget.consommer_llm(0.0, 1, 1)
        return reponse(EXTRACTION if len(vues) == 1 else TRI, cout=0.0)

    monkeypatch.setattr(graphe, "appeler_llm", espion)
    monkeypatch.setattr(graphe, "_client", lambda: FauxClient())
    monkeypatch.setattr(config, "MAX_TOURS", 0)  # cut short after triage
    graphe.demarrer("alerte", "t-classif", db)

    assert vues[0] is Classification.CONFIDENTIEL
    assert vues[1] is Classification.DERIVE


def test_la_liste_blanche_tient_dans_le_noeud_d_outils(monkeypatch, db):
    """A tool outside the allowlist does not reach the server, in the graph too.

    The client here is the REAL `ClientRunbooks`, never started: its
    session is closed, so if the refusal did not precede the access, the
    call would raise `ErreurOutil` instead of returning a message to the
    model.
    """
    client = outils.ClientRunbooks()
    scenariser(
        monkeypatch,
        [
            reponse(EXTRACTION),
            reponse(TRI),
            reponse(appels_outils=[appel_outil("ecrire_runbook", "c1")]),
            reponse(DIAGNOSTIC),
        ],
        client,
    )
    rapport = graphe.demarrer("alerte", "t-blanche", db)

    assert rapport.statut == "en_attente_humain"
    messages = graphe.etat("t-blanche", db)["valeurs"]["messages"]
    resultat = next(m for m in messages if m.get("role") == "tool")
    assert "Refusé" in resultat["content"]
    assert "ecrire_runbook" in resultat["content"]


# --- Reducers --------------------------------------------------------------


def test_les_accumulateurs_ne_s_ecrasent_pas(monkeypatch, db):
    """Two tool turns: the second does not overwrite the first."""
    client = FauxClient()
    scenariser(
        monkeypatch,
        [
            reponse(EXTRACTION),
            reponse(TRI),
            reponse(appels_outils=[appel_outil("semantic_search", "c1")]),
            reponse(appels_outils=[appel_outil("read_runbook", "c2")]),
            reponse(DIAGNOSTIC),
        ],
        client,
    )
    graphe.demarrer("alerte", "t-accum", db)
    instantane = graphe.etat("t-accum", db)

    assert instantane["valeurs"]["outils_appeles"] == ["semantic_search", "read_runbook"]
    assert instantane["journal"].count("raisonnement") == 3
    assert instantane["journal"].count("recherche_runbooks") == 2


def test_le_budget_est_rejoue_a_l_identique():
    """The budget survives serialisation because it is stored as deltas."""
    etat = {
        "depenses": [
            {"appels_llm": 1, "cout_usd": 0.10, "tokens_entree": 100, "tokens_sortie": 20},
            {"appels_llm": 1, "cout_usd": 0.05, "appels_outils": 2},
        ]
    }
    budget = graphe._budget(etat)
    assert budget.appels_llm == 2
    assert budget.appels_outils == 2
    assert budget.cout_usd == pytest.approx(0.15)
    assert budget.max_cout_usd == config.MAX_COUT_USD


def test_la_relance_est_une_arete_pas_un_except(monkeypatch, db):
    """Prose then JSON: two passes through `diagnostic`, both traced."""
    scenariser(
        monkeypatch,
        [
            reponse(EXTRACTION),
            reponse(TRI),
            reponse("Voici mon analyse en prose, sans JSON."),
            reponse(DIAGNOSTIC),
        ],
    )
    graphe.demarrer("alerte", "t-relance", db)
    journal = graphe.etat("t-relance", db)["journal"]

    assert journal.count("diagnostic") == 2
    assert journal.count("raisonnement") == 2


def test_le_chemin_parcouru_est_lisible_dans_l_etat(monkeypatch, db):
    scenariser(monkeypatch, [reponse(EXTRACTION), reponse(TRI), reponse(DIAGNOSTIC)])
    graphe.demarrer("alerte", "t-chemin", db)
    assert graphe.etat("t-chemin", db)["journal"] == [
        "extraction",
        "classification",
        "raisonnement",
        "diagnostic",
    ]


# --- The purge: retention of derived data --------------------------------


def _fil_en_pause(monkeypatch, db: str, thread_id: str) -> None:
    scenariser(
        monkeypatch,
        [
            reponse(EXTRACTION),
            reponse(TRI),
            reponse(appels_outils=[appel_outil("semantic_search", "c1")]),
            reponse(DIAGNOSTIC),
        ],
    )
    rapport = graphe.demarrer("PostgreSQL: too many clients already", thread_id, db)
    assert rapport.statut == "en_attente_humain"


def test_la_purge_conserve_un_fil_plus_recent_que_le_seuil(monkeypatch, db):
    """A thread from today survives a 14-day retention, even when paused."""
    _fil_en_pause(monkeypatch, db, "t-recent")

    bilan = graphe.purger(14, db)

    assert bilan["purges"] == []
    assert bilan["conserves"] == 1
    assert graphe.etat("t-recent", db)["existe"]


def test_la_simulation_liste_sans_supprimer(monkeypatch, db):
    _fil_en_pause(monkeypatch, db, "t-sim")
    dans_quinze_jours = datetime.now(UTC) + timedelta(days=15)

    bilan = graphe.purger(14, db, simulation=True, maintenant=dans_quinze_jours)

    assert [p["thread_id"] for p in bilan["purges"]] == ["t-sim"]
    assert bilan["purges"][0]["en_pause"] is True  # flagged, not spared
    assert graphe.etat("t-sim", db)["existe"]


def test_la_purge_supprime_le_fil_ancien_et_compacte_le_fichier(monkeypatch, db):
    """After a purge: no row, no free page, no WAL: the data is gone."""
    _fil_en_pause(monkeypatch, db, "t-vieux")
    dans_quinze_jours = datetime.now(UTC) + timedelta(days=15)

    bilan = graphe.purger(14, db, maintenant=dans_quinze_jours)

    assert [p["thread_id"] for p in bilan["purges"]] == ["t-vieux"]
    assert bilan["conserves"] == 0
    assert bilan["octets_apres"] <= bilan["octets_avant"]
    if os.path.exists(db + "-wal"):
        assert os.path.getsize(db + "-wal") == 0
    connexion = sqlite3.connect(db)
    assert connexion.execute("SELECT count(*) FROM checkpoints").fetchone()[0] == 0
    assert connexion.execute("SELECT count(*) FROM writes").fetchone()[0] == 0
    assert connexion.execute("PRAGMA freelist_count").fetchone()[0] == 0
    connexion.close()
    assert not graphe.etat("t-vieux", db)["existe"]


def test_la_purge_ne_cree_pas_le_fichier(tmp_path):
    absent = str(tmp_path / "jamais-cree.sqlite")
    bilan = graphe.purger(14, absent)
    assert bilan["purges"] == [] and bilan["conserves"] == 0
    assert not os.path.exists(absent)


def test_le_cli_purge_a_zero_jour(monkeypatch, db, capsys):
    _fil_en_pause(monkeypatch, db, "t-cli")

    code = cli_graphe.main(["--purger", "--avant", "0", "--checkpoints", db, "--json"])

    assert code == 0
    bilan = json.loads(capsys.readouterr().out)
    assert [p["thread_id"] for p in bilan["purges"]] == ["t-cli"]
    assert not graphe.etat("t-cli", db)["existe"]


def test_le_cli_refuse_simulation_sans_purger(db):
    with pytest.raises(SystemExit) as sortie:
        cli_graphe.main(["--simulation", "--checkpoints", db, "alerte"])
    assert sortie.value.code == 2
