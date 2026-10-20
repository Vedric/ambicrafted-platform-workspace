"""Adversarial arithmetic and the real review boundary, without network access."""

import copy
import json
import secrets

import httpx
import pytest
from test_graphe import DIAGNOSTIC, EXTRACTION, REVUE, TRI, FauxClient, appel_outil, completer_revue

from sre_agent import agent, config, graphe, llm
from sre_agent.budget import Budget, BudgetEpuise
from sre_agent.modeles import Confiance, Diagnostic, Extraction, appliquer_garde_source
from sre_agent.qualite import (
    Calcul,
    Revue,
    VerificationImpossible,
    extraction_retenue,
    indexer_operandes,
    indexer_propositions,
    verifier_calcul,
    verifier_diagnostic,
)


def calcul(valeur_gauche, valeur_droite, resultat, operation="comparaison", **modifications):
    valeur = {
        "champ": "diagnostic.cause_probable",
        "citation": "claim",
        "operation": operation,
        "gauche": {"contexte": f"A = {valeur_gauche};", "valeur": valeur_gauche},
        "droite": {"contexte": f"B = {valeur_droite};", "valeur": valeur_droite},
        "resultat_annonce": resultat,
    }
    valeur.update(modifications)
    return Calcul.model_validate(valeur)


def original(c):
    return c.gauche.contexte + " " + c.droite.contexte


@pytest.mark.parametrize(
    "gauche,droite,resultat",
    [
        ("27 minutes", "1800s", "<"),
        ("1,25 heures", "4500 s", "="),
        ("1073 MiB", "1GiB", ">"),
        ("1 GB", "1 GiB", "<"),
        ("0,025%", "0.02%", ">"),
        ("1\u202f024", "1023", ">"),
        ("-4", "-2", "<"),
        ("2026-01-01T13:00:00+02:00", "2026-01-01T11:00:00Z", "="),
        ("2026-01-01T23:59:59Z", "2026-01-02T00:00:00Z", "<"),
    ],
)
def test_comparisons_use_actual_units_and_timezone(gauche, droite, resultat):
    c = calcul(gauche, droite, resultat)
    rendu, conforme = verifier_calcul(c, original(c))
    assert conforme
    assert f"→ {resultat}" in rendu
    assert "A =" not in rendu  # The review's raw source quotation is not persisted.
    assert not verifier_calcul(c.model_copy(update={"resultat_annonce": "wrong"}), original(c))[1]


@pytest.mark.parametrize(
    "gauche,droite,operation,resultat",
    [
        ("7", "2000", "pourcentage", "0.35"),
        ("0", "13", "pourcentage", "0"),
        ("125 ms", "100 ms", "ecart_relatif", "25"),
        ("0.6%", "0.2%", "difference", "0.4"),
        ("4 minutes", "20 s", "difference", "220"),
    ],
)
def test_arithmetic_is_decimal_and_never_supplied_by_model(gauche, droite, operation, resultat):
    c = calcul(gauche, droite, resultat, operation)
    assert verifier_calcul(c, original(c))[1]
    assert not verifier_calcul(c.model_copy(update={"resultat_annonce": "999"}), original(c))[1]


def test_positive_rate_cannot_round_to_a_false_zero():
    c = calcul("7", "2000", "0", "pourcentage")
    rendered, matches = verifier_calcul(c, original(c))
    assert not matches
    assert "0.35 %" in rendered


@pytest.mark.parametrize(
    "gauche,droite,operation,reason",
    [
        ("1 ms", "1 MiB", "comparaison", "dimensions_incompatibles"),
        ("1", "0", "pourcentage", "denominateur_nul"),
        ("10:04", "10:02", "comparaison", "format_operande_non_supporte"),
        ("1 month", "30", "comparaison", "unite_non_supportee"),
        ("1e1000000", "2", "comparaison", "format_operande_non_supporte"),
        ("10000000000000000000", "2", "comparaison", "nombre_hors_limites"),
        ("__import__('os')", "2", "comparaison", "format_operande_non_supporte"),
    ],
)
def test_unsupported_operations_fail_closed(gauche, droite, operation, reason):
    c = calcul(gauche, droite, "1", operation)
    with pytest.raises(VerificationImpossible, match=reason):
        verifier_calcul(c, original(c))


@pytest.mark.parametrize(
    "contexte,valeur,raw",
    [
        ("2", "2", "A = 12; B = 3;"),
        ("A = 2 heures;", "2", "A = 2 heures; B = 3;"),
        ("A = 12;", "2", "A = 12; B = 3;"),
        ("A = 0.5;", "0", "A = 0.5; B = 3;"),
        ("A = 2;", "2", "A = 12; B = 3;"),
    ],
)
def test_substrings_missing_units_and_forged_source_are_refused(contexte, valeur, raw):
    c = calcul("2", "3", "<", gauche={"contexte": contexte, "valeur": valeur})
    with pytest.raises(VerificationImpossible):
        verifier_calcul(c, raw)


def test_nested_review_schema_is_closed_and_cannot_create_actions():
    schema = Revue.model_json_schema()
    for definition in (schema, *schema["$defs"].values()):
        if definition.get("type") == "object":
            assert definition["additionalProperties"] is False
            assert set(definition["required"]) == set(definition["properties"])
    for extra in ({"actions_proposees": ["delete"]}, {"confiance_max": "haute"}):
        with pytest.raises(ValueError):
            Revue.model_validate({**json.loads(REVUE), **extra})


class Client(FauxClient):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


@pytest.mark.parametrize("engine", [agent, graphe], ids=["loop", "graph"])
@pytest.mark.parametrize("reason", ["execution", "attribution", "portee"])
def test_real_boundary_review_vetoes_unsupported_conclusion_before_approval(
    monkeypatch, tmp_path, engine, reason
):
    marker = secrets.token_hex(18)
    alert = f"Planned change only; no deployment applied. {marker}"
    draft = json.loads(DIAGNOSTIC)
    draft["cause_probable"] = "The change was applied and caused an outage."
    draft["actions_proposees"].append("An invented procedure that no source provides.")
    review = {
        **json.loads(REVUE),
        "examens": [
            {
                "reference": "p3",
                "nature": reason,
            }
        ],
    }
    replies = [EXTRACTION, TRI, None, json.dumps(draft), json.dumps(review)]
    requests = []
    client = Client()
    monkeypatch.setattr(agent, "ClientRunbooks", lambda: client)
    monkeypatch.setattr(graphe, "_client", lambda: client)
    monkeypatch.setenv("CONFIDENTIAL_KEY", secrets.token_urlsafe(24))

    def post(_url, **kwargs):
        requests.append(copy.deepcopy(kwargs["json"]))
        reply = replies.pop(0)
        if len(requests) == 5:
            schema = kwargs["json"]["response_format"]["json_schema"]["schema"]
            reply = json.dumps(completer_revue(schema, json.loads(reply)))
        message = (
            {"content": reply}
            if reply is not None
            else {"tool_calls": [appel_outil("read_runbook", "read")]}
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": message}],
                "usage": {"prompt_tokens": 70, "completion_tokens": 20},
            },
        )

    monkeypatch.setattr(llm, "_poster_borne", post)
    if engine is graphe:
        db = str(tmp_path / "state.sqlite")
        pending = graphe.demarrer(alert, "review", db)
        assert pending.statut == "en_attente_humain"
        proposal = json.loads(pending.message)
        assert proposal["qualite"]["statut"] == "abstention"
        assert proposal["actions_proposees"] == []
        assert draft["cause_probable"] not in pending.message
        report = graphe.reprendre("oui", "review", db)
        assert marker not in json.dumps(graphe.etat("review", db), default=str)
        assert all(
            marker.encode() not in path.read_bytes()
            for path in tmp_path.iterdir()
            if path.is_file()
        )
    else:
        report = agent.analyser(alert)
    assert report.statut == "complet"
    assert report.diagnostic.qualite.statut == "abstention"
    assert report.diagnostic.actions_proposees == []
    assert report.diagnostic.runbook_source is None
    assert report.budget["appels_llm"] == 5
    assert report.diagnostic.qualite.tokens_entree == 70
    assert report.diagnostic.qualite.tokens_sortie == 20
    assert len(requests) == 5
    assert requests[-1]["model"] == "local"
    assert "tools" not in requests[-1]
    assert marker in json.dumps(requests[-1]["messages"])
    review_prompt = requests[-1]["messages"][-1]["content"]
    assert '"actions_deja_rejetees_par_garde_source": 1' in review_prompt
    generated, _ = appliquer_garde_source(Diagnostic.model_validate(draft), {})
    assert generated.elements_manquants[-1] not in review_prompt
    assert marker not in report.model_dump_json()


def revue_http(monkeypatch, review, observations="A = 27 minutes; B = 1 heure;", *, complete=True):
    monkeypatch.setenv("CONFIDENTIAL_KEY", secrets.token_urlsafe(24))

    def post(_url, **kwargs):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                completer_revue(
                                    kwargs["json"]["response_format"]["json_schema"]["schema"],
                                    review,
                                )
                                if complete
                                else review
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            },
        )

    monkeypatch.setattr(llm, "_poster_borne", post)
    return lambda diagnostic=None, budget=None: verifier_diagnostic(
        diagnostic or Diagnostic.model_validate_json(DIAGNOSTIC),
        Extraction.model_validate_json(EXTRACTION),
        observations,
        budget or Budget(10, 1),
        appel=llm.appeler_llm,
    )


def test_mathematical_contradiction_overrides_a_reviewer_that_says_enough_evidence(monkeypatch):
    claim = {
        "reference": "p3",
        "operation": "comparaison",
        "gauche": "n0",
        "droite": "n1",
        "resultat_annonce": ">",
    }
    check = revue_http(monkeypatch, {**json.loads(REVUE), "calculs": [claim]})
    result = check()
    assert result.qualite.statut == "abstention"
    assert "diagnostic.cause_probable:calcul_contredit" in result.qualite.ecarts
    assert "→ <" in result.qualite.calculs[0]
    assert not result.actions_proposees


def test_forged_citation_and_malformed_review_cannot_silently_pass(monkeypatch):
    for review in (
        {},
        {
            **json.loads(REVUE),
            "examens": [
                {
                    "reference": "p999",
                    "nature": "execution",
                }
            ],
        },
    ):
        result = revue_http(monkeypatch, review)()
        assert result.qualite.statut == "abstention"
        assert result.qualite.extraction_ecartee


def test_review_can_never_upgrade_confidence_or_mutate_actions(monkeypatch):
    diagnostic = Diagnostic.model_validate_json(DIAGNOSTIC)
    diagnostic.confiance = Confiance.FAIBLE
    result = revue_http(monkeypatch, json.loads(REVUE))(diagnostic)
    assert result.qualite.statut == "revue_ia_sans_ecart_bloquant"
    assert result.confiance == "faible"
    assert result.actions_proposees == diagnostic.actions_proposees
    assert result.runbook_source == diagnostic.runbook_source


def test_final_review_still_enforces_token_and_time_limits(monkeypatch):
    check = revue_http(monkeypatch, json.loads(REVUE))
    with pytest.raises(BudgetEpuise):
        check(budget=Budget(10, 1, max_tokens_total=25))
    with pytest.raises(BudgetEpuise):
        check(budget=Budget(10, 1, echeance=0))


def test_review_cannot_send_original_to_frontier(monkeypatch):
    check = revue_http(monkeypatch, json.loads(REVUE))
    monkeypatch.setattr(config, "ALIAS_RAISONNEMENT", "smart")
    with pytest.raises(llm.FuiteConfidentielle):
        check()


def test_bad_search_summary_is_removed_without_discarding_a_consistent_final_answer(monkeypatch):
    review = {
        **json.loads(REVUE),
        "examens": [
            {
                "reference": "p1",
                "nature": "preuve_absente",
            }
        ],
    }
    result = revue_http(monkeypatch, review)()
    assert result.qualite.statut == "revue_ia_sans_ecart_bloquant"
    assert result.qualite.extraction_ecartee
    retained = extraction_retenue(Extraction.model_validate_json(EXTRACTION), result)
    assert not retained.symptomes
    assert "écarté" in retained.signature_technique
    assert result.cause_probable == json.loads(DIAGNOSTIC)["cause_probable"]


def test_missing_original_is_an_explicit_abstention_without_network():
    result = verifier_diagnostic(
        Diagnostic.model_validate_json(DIAGNOSTIC),
        Extraction.model_validate_json(EXTRACTION),
        None,
        Budget(10, 1),
        appel=lambda **_: pytest.fail("Missing evidence must not trigger a model request"),
    )
    assert result.qualite.statut == "abstention"
    assert result.qualite.tokens_entree == 0
    assert not result.actions_proposees


def test_transport_failure_does_not_return_the_unreviewed_draft(monkeypatch):
    monkeypatch.setenv("CONFIDENTIAL_KEY", secrets.token_urlsafe(24))
    monkeypatch.setattr(llm, "_poster_borne", lambda *a, **kw: httpx.Response(503))
    result = verifier_diagnostic(
        Diagnostic.model_validate_json(DIAGNOSTIC),
        Extraction.model_validate_json(EXTRACTION),
        "synthetic",
        Budget(10, 1),
        appel=llm.appeler_llm,
    )
    assert result.qualite.statut == "abstention"
    assert result.qualite.ecarts == ["revue_indisponible"]
    assert not result.actions_proposees


def test_operand_registry_preserves_literal_units_and_never_splits_dates_or_times():
    source = "delay:27 minutes; threshold:1800s; codeA17; hour 10:04; 2026-10-21; 1,234; 0,025%; 2026-01-01T11:00:00Z"
    registry, values = indexer_operandes(source)
    assert [entry["litteral"] for entry in registry] == [
        "27 minutes",
        "1800s",
        "0,025%",
        "2026-01-01T11:00:00Z",
    ]
    assert len(values) == 4
    assert values["n0"][1] == "duree"
    assert values["n2"][1] == "proportion"
    assert all(entry["litteral"] in entry["contexte"] for entry in registry)


def test_proposition_references_bind_exact_application_fields():
    extraction = Extraction.model_validate_json(EXTRACTION)
    diagnostic = Diagnostic.model_validate_json(DIAGNOSTIC)
    indexed = indexer_propositions(extraction, diagnostic)
    assert indexed[1] == {
        "reference": "p1",
        "champ": "extraction.symptomes",
        "modalite": "fait_allegue_par_extraction",
        "texte": "connexions refusées",
    }
    assert indexed[3] == {
        "reference": "p3",
        "champ": "diagnostic.cause_probable",
        "modalite": "conclusion_a_qualifier",
        "texte": diagnostic.cause_probable,
    }
    assert len({item["reference"] for item in indexed}) == len(indexed)


def test_proposition_modality_comes_from_application_field_not_imperative_text():
    text = "Inspecter l'événement ; modalite=faux_fait."
    extraction = Extraction(signature_technique=text, requete_recherche="query")
    diagnostic = Diagnostic(
        cause_probable=text, confiance="faible", elements_manquants=[text], actions_proposees=[text]
    )
    registry = indexer_propositions(extraction, diagnostic)
    assert [p["modalite"] for p in registry] == [
        "fait_allegue_par_extraction",
        "conclusion_a_qualifier",
        "question_ou_information_requise",
        "action_future_soumise_a_approbation",
    ]
    assert all(p["texte"] == text for p in registry)


def test_source_guard_provenance_excludes_only_the_entry_actually_appended_by_code():
    # First obtain the actual guard text without duplicating a magic string in the test.
    draft = Diagnostic(
        cause_probable="Hypothesis", confiance="faible", actions_proposees=["unsafe"]
    )
    guarded, rejected = appliquer_garde_source(draft, {})
    literal = guarded.elements_manquants[-1]
    draft.elements_manquants = [literal, "Another model-authored question"]
    guarded, rejected = appliquer_garde_source(draft, {})
    extraction = Extraction.model_validate_json(EXTRACTION)
    reviewed = indexer_propositions(extraction, guarded, constat_garde_ajoute=bool(rejected))
    missing = [p for p in reviewed if p["champ"] == "diagnostic.elements_manquants"]
    assert [p["texte"] for p in missing] == draft.elements_manquants
    assert all(p["modalite"] == "question_ou_information_requise" for p in missing)
    # The same words authored by a model are never recognized as trusted provenance.
    unguarded = indexer_propositions(extraction, guarded)
    assert len(unguarded) == len(reviewed) + 1


def test_bounded_calculation_chain_compares_a_computed_rate_to_a_literal_threshold(monkeypatch):
    review = {
        **json.loads(REVUE),
        "calculs": [
            {
                "reference": "p3",
                "operation": "pourcentage",
                "gauche": "n0",
                "droite": "n1",
                "resultat_annonce": "0.35",
            },
            {
                "reference": "p3",
                "operation": "comparaison",
                "gauche": "c0",
                "droite": "n2",
                "resultat_annonce": ">",
            },
        ],
    }
    diagnostic = Diagnostic(cause_probable="7/2000 = 0.35% > 0.2%", confiance="moyenne")
    result = revue_http(monkeypatch, review, "7 errors over 2000 requests; threshold 0.2%.")(
        diagnostic
    )
    assert result.qualite.statut == "revue_ia_sans_ecart_bloquant"
    assert len(result.qualite.calculs) == 2
    assert "0.35 %" in result.qualite.calculs[0]
    assert "→ >" in result.qualite.calculs[1]


@pytest.mark.parametrize("reference", ["c0", "c1", "n9"])
def test_unknown_forward_and_cyclic_numeric_references_are_refused(monkeypatch, reference):
    review = {
        **json.loads(REVUE),
        "calculs": [
            {
                "reference": "p3",
                "operation": "comparaison",
                "gauche": reference,
                "droite": "n1",
                "resultat_annonce": ">",
            }
        ],
    }
    result = revue_http(monkeypatch, review)()
    assert result.qualite.statut == "abstention"
    assert "reference_operande_invalide" in result.qualite.ecarts


def test_reference_cannot_redefine_the_value_or_unit(monkeypatch):
    review = {
        **json.loads(REVUE),
        "calculs": [
            {
                "reference": "p3",
                "operation": "comparaison",
                "gauche": "n0",
                "droite": "n1",
                "resultat_annonce": ">",
                "unite": "hours",
            }
        ],
    }
    result = revue_http(monkeypatch, review)()
    assert result.qualite.statut == "abstention"
    assert "revue_indisponible" in result.qualite.ecarts


def test_ambiguous_locale_and_excessive_precision_are_not_silently_rounded():
    for number in ("1,234", "0.1234567890123456789012345"):
        c = calcul(number, "2", "<")
        with pytest.raises(VerificationImpossible):
            verifier_calcul(c, original(c))


def test_large_numeric_registry_fails_explicitly_instead_of_silently_omitting_evidence():
    with pytest.raises(VerificationImpossible, match="trop_de_quantites"):
        indexer_operandes("; ".join(f"value={number}" for number in range(65)))


@pytest.mark.parametrize("mode", ["missing", "duplicate", "unknown"])
def test_every_proposal_requires_exactly_one_review_verdict(monkeypatch, mode):
    entries = [{"reference": f"p{i}", "nature": "aucun"} for i in range(5)]
    if mode == "missing":
        entries.pop()
    elif mode == "duplicate":
        entries[-1] = entries[0]
    else:
        entries[-1] = {"reference": "p999", "nature": "aucun"}
    review = {**json.loads(REVUE), "examens": entries}
    result = revue_http(monkeypatch, review, complete=False)()
    assert result.qualite.statut == "abstention"
    assert "couverture_revue_incomplete_ou_dupliquee" in result.qualite.ecarts
    assert not result.actions_proposees


def test_excessive_proposal_count_refuses_review_before_model(monkeypatch):
    diagnostic = Diagnostic.model_validate_json(DIAGNOSTIC)
    diagnostic.elements_manquants = [f"Missing observation {n}" for n in range(48)]
    result = verifier_diagnostic(
        diagnostic,
        Extraction.model_validate_json(EXTRACTION),
        "synthetic",
        Budget(10, 1),
        appel=lambda **_: pytest.fail("Oversized proposal registry must stop before inference"),
    )
    assert result.qualite.statut == "abstention"
    assert result.qualite.ecarts == ["trop_de_propositions"]
