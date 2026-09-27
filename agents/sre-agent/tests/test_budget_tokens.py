"""Observed token accounting, strict telemetry parsing and refusal before dispatch."""

import json
import math

import httpx
import pytest

from sre_agent import cli, cli_graphe, config, graphe, llm
from sre_agent.budget import Budget, BudgetEpuise
from sre_agent.modeles import Rapport


@pytest.fixture
def repondre(monkeypatch):
    monkeypatch.setenv("CONFIDENTIAL_KEY", "synthetic-local-fixture")
    appels = []

    def installer(usage):
        def post(*_args, **kwargs):
            appels.append(kwargs["json"])
            return httpx.Response(
                200,
                json={
                    "usage": usage,
                    "choices": [{"message": {"content": "{}"}}],
                },
            )

        monkeypatch.setattr(llm.httpx, "post", post)
        return appels

    return installer


def appeler(budget, **kwargs):
    return llm.appeler_llm(
        alias="local",
        messages=[{"role": "user", "content": "Synthetic alert"}],
        classification=config.Classification.CONFIDENTIEL,
        budget=budget,
        tache="test",
        **kwargs,
    )


def test_plafond_exact_refuse_appel_suivant_avant_http(repondre):
    appels = repondre({"prompt_tokens": 6, "completion_tokens": 4})
    budget = Budget(10, 1, max_tokens_total=10)
    appeler(budget)
    with pytest.raises(BudgetEpuise, match="jetons observés atteint"):
        appeler(budget)
    assert len(appels) == 1
    assert budget.resume()["tokens_total"] == 10
    assert budget.resume()["usage_complet"] is True


def test_depassement_apres_reponse_conserve_la_depense_reelle(repondre):
    appels = repondre({"prompt_tokens": 11, "completion_tokens": 4})
    budget = Budget(10, 1, max_tokens_total=10)
    with pytest.raises(BudgetEpuise, match="jetons observés dépassé"):
        appeler(budget)
    assert len(appels) == 1
    assert budget.appels_llm == 1 and budget.tokens_entree == 11
    assert budget.resume()["tokens_total"] == 15
    with pytest.raises(BudgetEpuise):
        appeler(budget)
    assert len(appels) == 1


@pytest.mark.parametrize("usage", [None, {}, {"prompt_tokens": None, "completion_tokens": None}])
def test_usage_absent_est_inconnu_pas_zero(repondre, usage):
    repondre(usage)
    budget = Budget(10, 1)
    reponse = appeler(budget)
    assert reponse.tokens_entree is None and reponse.tokens_sortie is None
    resume = budget.resume()
    assert resume["tokens_entree"] is None and resume["tokens_sortie"] is None
    assert resume["tokens_total"] is None and resume["appels_llm"] == 1
    assert resume["tokens_disponibles"] is False and resume["usage_complet"] is False
    assert resume["appels_mesures_tokens"] == 0
    rapport = Rapport(statut="erreur", budget=resume)
    assert rapport.model_dump()["budget"]["tokens_total"] is None
    assert rapport.model_dump()["budget"]["usage_complet"] is False


def test_usage_partiel_est_somme_observee_et_completude_par_direction(repondre):
    budget = Budget(10, 1)
    repondre({"prompt_tokens": 20})
    appeler(budget)
    resume = budget.resume()
    assert resume["tokens_entree"] == 20 and resume["tokens_sortie"] is None
    assert resume["tokens_total"] == 20 and resume["tokens_disponibles"] is True
    assert resume["usage_complet"] is False and resume["appels_mesures_entree"] == 1
    assert resume["appels_mesures_sortie"] == 0 and resume["appels_mesures_tokens"] == 0
    repondre({"prompt_tokens": 2, "completion_tokens": 0})
    appeler(budget)
    resume = budget.resume()
    assert resume["tokens_total"] == 22 and resume["tokens_sortie"] == 0
    assert resume["usage_complet"] is False
    assert resume["appels_mesures_tokens"] == 1 and resume["appels_llm"] == 2


def test_zero_reel_fourni_reste_une_mesure(repondre):
    repondre({"prompt_tokens": 0, "completion_tokens": 0})
    budget = Budget(10, 1)
    appeler(budget)
    assert budget.resume()["tokens_total"] == 0
    assert budget.resume()["tokens_disponibles"] is True
    assert budget.resume()["usage_complet"] is True


@pytest.mark.parametrize("valeur", [-1, True, 1.5, "12", math.inf, math.nan, [], {}])
def test_usage_invalide_refuse_sans_inventer_mesure(monkeypatch, valeur):
    monkeypatch.setenv("CONFIDENTIAL_KEY", "synthetic-fixture")

    # Non-finite JSON is deliberate hostile provider input, not a valid encoder output.
    class Reponse:
        status_code = 200
        headers = httpx.Headers()

        def json(self):
            return {"usage": {"prompt_tokens": valeur}, "choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(llm.httpx, "post", lambda *_a, **_k: Reponse())
    budget = Budget(10, 1)
    with pytest.raises(llm.ErreurPasserelle, match="mal formée"):
        appeler(budget)
    assert budget.appels_llm == 1
    assert budget.resume()["tokens_total"] is None
    assert budget.resume()["appels_mesures_tokens"] == 0


@pytest.mark.parametrize("usage", [[], "unknown", 10, False])
def test_usage_non_objet_refuse(repondre, usage):
    repondre(usage)
    with pytest.raises(llm.ErreurPasserelle):
        appeler(Budget(10, 1))


@pytest.mark.parametrize("valeur", [-1, 0, True, 1.5, 1_000_001])
def test_plafond_cumulatif_borne(valeur):
    with pytest.raises(ValueError):
        Budget(10, 1, max_tokens_total=valeur)


@pytest.mark.parametrize("valeur", [0, -1, True, 6_001])
def test_completion_bornee_avant_dispatch(repondre, valeur):
    appels = repondre({})
    with pytest.raises(llm.ErreurPasserelle, match="Plafond de réponse"):
        appeler(Budget(10, 1), max_tokens=valeur)
    assert appels == []


def test_reprise_graphe_conserve_compteurs_et_bloque_au_plafond(monkeypatch):
    monkeypatch.setattr(config, "MAX_TOKENS_TOTAL", 12)
    original = Budget(config.MAX_APPELS_OUTILS, config.MAX_COUT_USD)
    avant = graphe._instantane(original)
    original.consommer_llm(0, 10, None)
    premiere = graphe._delta(avant, original)
    avant = graphe._instantane(original)
    original.consommer_llm(0, 1, 1)
    seconde = graphe._delta(avant, original)
    repris = graphe._budget({"depenses": [premiere, seconde]})
    assert repris.resume() == original.resume()
    with pytest.raises(BudgetEpuise, match="jetons observés"):
        repris.verifier_avant_llm()


def test_checkpoint_historique_ne_devient_pas_usage_complet():
    repris = graphe._budget({"depenses": [{"appels_llm": 1, "tokens_entree": 10}]})
    assert repris.resume()["tokens_entree"] == 10
    assert repris.resume()["usage_complet"] is False
    assert repris.resume()["appels_mesures_tokens"] == 0


@pytest.mark.parametrize("erreur", ["timeout", "http", "cout"])
def test_tentative_sans_mesures_reste_inconnue_et_checkpointable(monkeypatch, erreur):
    monkeypatch.setenv("CONFIDENTIAL_KEY", "synthetic-fixture")

    def repondre(*_a, **_k):
        if erreur == "timeout":
            raise httpx.ReadTimeout("PRIVATE_SYNTHETIC_MESSAGE")
        return (
            httpx.Response(503)
            if erreur == "http"
            else httpx.Response(200, headers={"x-litellm-response-cost": "NaN"})
        )

    monkeypatch.setattr(llm.httpx, "post", repondre)
    budget = Budget(config.MAX_APPELS_OUTILS, config.MAX_COUT_USD)
    avant = graphe._instantane(budget)
    with pytest.raises(llm.ErreurPasserelle) as capture:
        appeler(budget)
    assert "PRIVATE_SYNTHETIC_MESSAGE" not in str(capture.value)
    resume = budget.resume()
    assert resume["appels_llm_tentes"] == 1 and resume["appels_llm"] == 0
    assert resume["tokens_total"] is None and resume["cout_usd"] is None
    assert resume["usage_complet"] is False and resume["usage_cout_complet"] is False
    assert graphe._budget({"depenses": [graphe._delta(avant, budget)]}).resume() == resume


def test_cout_local_absent_pas_zero_et_cout_zero_explicitement_mesure(monkeypatch):
    monkeypatch.setenv("CONFIDENTIAL_KEY", "synthetic-fixture")
    reponses = iter(
        [
            httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]}),
            httpx.Response(
                200,
                headers={"x-litellm-response-cost": "0"},
                json={"choices": [{"message": {"content": "{}"}}]},
            ),
        ]
    )
    monkeypatch.setattr(llm.httpx, "post", lambda *_a, **_k: next(reponses))
    budget = Budget(10, 1)
    appeler(budget)
    assert budget.resume()["cout_usd"] is None
    assert budget.resume()["cout_disponible"] is False
    appeler(budget)
    resume = budget.resume()
    assert resume["cout_usd"] == 0 and resume["cout_disponible"] is True
    assert resume["usage_cout_complet"] is False and resume["appels_mesures_cout"] == 1
    assert resume["appels_llm_tentes"] == 2


def test_checkpoint_historique_et_tentative_interrompue_additionnent_couverture():
    repris = graphe._budget(
        {"depenses": [{"appels_llm": 2, "cout_usd": 0.1}, {"appels_llm_tentes": 1}]}
    )
    assert repris.resume()["appels_llm_tentes"] == 3
    assert repris.resume()["cout_usd"] == 0.1
    assert repris.resume()["usage_cout_complet"] is False


def test_rendus_cli_rapport_et_pause_supportent_usage_inconnu():
    budget = Budget(10, 1)
    budget.consommer_llm(None, None, None)
    resume = budget.resume()
    normal = cli.rendre(Rapport(statut="erreur", budget=resume))
    pause = cli_graphe.rendre_graphe(
        Rapport(statut="en_attente_humain", message=json.dumps({"budget": resume})),
        "fixture",
        "/tmp/fixture.sqlite",
    )
    for rendu in [normal, pause]:
        assert "coût API inconnu" in rendu and "JETONS OBSERVÉS : inconnus" in rendu
        assert "0/1 appels" in rendu
