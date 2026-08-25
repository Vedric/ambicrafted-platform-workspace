"""Tests du portage LangGraph, sur une machine débranchée.

Même exigence que `test_gardefous.py` : ni passerelle, ni serveur MCP, ni
réseau. Ce qui est vérifié ici n'est pas le framework — c'est que le
portage n'a rien desserré, et que les propriétés nouvelles (routage par
arête, pause durable) tiennent réellement.

Le point de substitution est `appeler_llm` et le client d'outils. Tout le
reste — budget, liste blanche, confinement, garde de source — est le code
de production, exécuté tel quel.
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

# --- Doublures -------------------------------------------------------------


class FauxClient:
    """Un serveur d'outils qui répond, et qui compte ce qu'on lui demande."""

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
    """Installe une suite de réponses LLM et un client d'outils factice.

    Le budget reste le vrai : la doublure l'impute comme le ferait la
    passerelle, ce qui laisse les plafonds pleinement opposables.
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


# --- La porte humaine, et la survie de l'état -----------------------------


def test_le_graphe_s_arrete_avant_de_livrer(monkeypatch, db):
    """Rien n'est livré tant qu'un humain n'a pas vu le diagnostic."""
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
    # Le diagnostic est SOUMIS, pas livré : la demande d'approbation le
    # porte, et l'état ne contient aucune trace de décision humaine.
    demande = json.loads(rapport.message)
    assert demande["runbook_source"] == "incident-p1-database.md"
    assert demande["actions_proposees"] == ["Terminer les sessions idle"]

    instantane = graphe.etat("t-porte", db)
    assert instantane["prochains_noeuds"] == ["porte_humaine"]
    assert instantane["valeurs"].get("approbation") is None
    assert instantane["valeurs"].get("statut") == "en_cours"
    assert instantane["en_attente"]  # le checkpoint sait qu'il attend


def test_la_reprise_repart_du_meme_point(monkeypatch, db):
    """Une application recompilée, sans aucune réponse LLM restante, aboutit.

    C'est la preuve que le contexte vient du checkpoint et non de la
    mémoire : la suite scénarisée est vide au moment de la reprise, donc
    aucun appel de modèle n'est possible.
    """
    scenariser(
        monkeypatch,
        [reponse(EXTRACTION), reponse(TRI), reponse(DIAGNOSTIC)],
    )
    graphe.demarrer("PostgreSQL: too many clients already", "t-reprise", db)

    # Plus une seule réponse disponible : tout doit venir de SQLite.
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
    """Un défaut permissif transformerait la porte en formalité."""
    scenariser(monkeypatch, [reponse(EXTRACTION), reponse(TRI), reponse(DIAGNOSTIC)])
    graphe.demarrer("alerte", "t-vide", db)
    scenariser(monkeypatch, [])
    assert graphe.reprendre("", "t-vide", db).statut == "rejete_par_humain"


# --- Budgets opposés par une arête, pas par une exception -----------------


def test_budget_outils_route_vers_abandon(monkeypatch, db):
    """Plafond à 2 : la salve de 3 outils est refusée, sans exception."""
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
    # Le motif désigne le bon plafond : « outils » et « tours » appellent
    # des corrections opposées, les confondre coûte du temps en astreinte.
    assert "plafond d'appels d'outils atteint" in rapport.message
    assert "salve de 3 outil(s)" in rapport.message
    assert "tours" not in rapport.message
    # Aucun outil n'a été exécuté : l'arête a décidé avant le nœud.
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
    # Message émis par budget.py lui-même : le garde-fou a levé dans le nœud,
    # l'arête n'a eu qu'à router. La reconstruction ne sert qu'aux refus
    # prononcés par l'arête avant même d'entrer dans le nœud.
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


# --- Le cloisonnement survit au portage -----------------------------------


def test_charge_confidentielle_refusee_dans_le_graphe(monkeypatch, db):
    """Le nœud d'extraction reste soumis à la garde de `llm.py`.

    Aucune doublure ici : c'est le vrai `appeler_llm` qui s'exécute, et
    le réseau est piégé pour prouver qu'il n'est jamais atteint.
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
    """La classification est passée par le nœud, pas déduite du graphe."""
    vues: list[Classification] = []

    def espion(*, classification, budget, **_k):
        vues.append(classification)
        budget.consommer_llm(0.0, 1, 1)
        return reponse(EXTRACTION if len(vues) == 1 else TRI, cout=0.0)

    monkeypatch.setattr(graphe, "appeler_llm", espion)
    monkeypatch.setattr(graphe, "_client", lambda: FauxClient())
    monkeypatch.setattr(config, "MAX_TOURS", 0)  # coupe court après le tri
    graphe.demarrer("alerte", "t-classif", db)

    assert vues[0] is Classification.CONFIDENTIEL
    assert vues[1] is Classification.DERIVE


def test_la_liste_blanche_tient_dans_le_noeud_d_outils(monkeypatch, db):
    """Un outil hors liste blanche n'atteint pas le serveur, dans le graphe aussi.

    Le client est ici le VRAI `ClientRunbooks`, jamais démarré : sa
    session est fermée, donc si le refus ne précédait pas l'accès, l'appel
    lèverait `ErreurOutil` au lieu de rendre un message au modèle.
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
    """Deux tours d'outils : le second n'écrase pas le premier."""
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
    """Le budget survit à la sérialisation parce qu'il est stocké en deltas."""
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
    """De la prose puis du JSON : deux passages par `diagnostic`, tracés."""
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


# --- La purge : rétention de la donnée dérivée ---------------------------


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
    """Un fil d'aujourd'hui survit à une rétention de 14 jours, même en pause."""
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
    assert bilan["purges"][0]["en_pause"] is True  # signalé, pas épargné
    assert graphe.etat("t-sim", db)["existe"]


def test_la_purge_supprime_le_fil_ancien_et_compacte_le_fichier(monkeypatch, db):
    """Après purge, ni ligne, ni page libre, ni WAL : la donnée est partie."""
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
