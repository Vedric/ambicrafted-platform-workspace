"""Repeated real source validation stops exploration without weakening delivery guards."""

import copy
import hashlib
import json
import secrets

import httpx
import pytest
from test_graphe import DIAGNOSTIC, EXTRACTION, REVUE, TRI, completer_revue

from sre_agent import agent, config, graphe, llm
from sre_agent.recherche import CONCLUSION_BORNEE, ProgressionRecherche


class Client:
    def __init__(self, *, malformed=False, change_at=None):
        self.appels = []
        self.malformed, self.change_at = malformed, change_at

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def outils_openai(self):
        return [
            {"type": "function", "function": {"name": name, "parameters": {"type": "object"}}}
            for name in ("read_runbook", "semantic_search")
        ]

    def appeler(self, nom, arguments):
        self.appels.append((nom, arguments))
        if nom != "read_runbook":
            return json.dumps({"source": "unread.md", "texte": "Search snippet is not a read"})
        text = "## Runbook\nTerminer les sessions idle."
        if self.change_at == len(self.appels):
            text += "\n\nNew source version with an additional condition."
        return json.dumps(
            {
                "fichier": arguments["nom"],
                "texte": text,
                "sha256": "invalid"
                if self.malformed
                else hashlib.sha256(text.encode()).hexdigest(),
                "tronque": False,
            }
        )


def execute(
    monkeypatch, tmp_path, engine, sequence, *, client=None, final=None, reject=False, cost=None
):
    client = client or Client()
    final = final or {"content": DIAGNOSTIC}
    captured = []
    original = "synthetic-original-" + secrets.token_hex(8)
    stages = [EXTRACTION, TRI]
    cursor = 0
    monkeypatch.setenv("CONFIDENTIAL_KEY", secrets.token_urlsafe(32))
    monkeypatch.setattr(agent, "ClientRunbooks", lambda: client)
    monkeypatch.setattr(graphe, "_client", lambda: client)

    def request(_url, **kwargs):
        nonlocal cursor
        body = copy.deepcopy(kwargs["json"])
        captured.append(body)
        schema = body.get("response_format", {}).get("json_schema", {}).get("schema", {})
        if stages:
            message = {"content": stages.pop(0)}
        elif "examens" in schema.get("properties", {}):
            review = json.loads(REVUE)
            review["preuves_suffisantes"] = not reject
            message = {"content": json.dumps(completer_revue(schema, review))}
        elif "cause_probable" in schema.get("properties", {}):
            message = final
        else:
            names = sequence[min(cursor, len(sequence) - 1)]
            cursor += 1
            message = {
                "tool_calls": [
                    {
                        "id": f"tool-{cursor}-{index}",
                        "function": {
                            "name": "semantic_search" if name == "search" else "read_runbook",
                            "arguments": json.dumps({"nom": name}),
                        },
                    }
                    for index, name in enumerate(names)
                ]
            }
        return httpx.Response(
            200,
            headers={} if cost is None else {"x-litellm-response-cost": str(cost)},
            json={
                "choices": [{"message": {"role": "assistant", **message}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 40},
            },
        )

    monkeypatch.setattr(llm, "_poster_borne", request)
    db = str(tmp_path / "checkpoint.sqlite")
    report = (
        agent.analyser(original)
        if engine is agent
        else graphe.demarrer(original, "synthetic-stagnation", db)
    )
    if engine is graphe:
        state = graphe.etat("synthetic-stagnation", db)
        assert original not in json.dumps(state, default=str)
    return report, captured, client


def finalisations(captured):
    return [
        body
        for body in captured
        if "cause_probable"
        in body.get("response_format", {})
        .get("json_schema", {})
        .get("schema", {})
        .get("properties", {})
    ]


def diagnostic(report):
    return (
        json.loads(report.message)
        if report.statut == "en_attente_humain"
        else report.diagnostic.model_dump()
    )


@pytest.mark.parametrize("engine", [agent, graphe], ids=["loop", "graph"])
def test_repeated_verified_reads_produce_one_structured_finalisation_and_real_review(
    monkeypatch, tmp_path, engine
):
    report, captured, client = execute(monkeypatch, tmp_path, engine, [["incident-p1-database.md"]])
    assert report.statut == ("complet" if engine is agent else "en_attente_humain")
    if engine is graphe:
        assert report.diagnostic is None  # Finalisation does not bypass human approval.
    assert len(client.appels) == 3
    assert len(captured) == 7
    final = finalisations(captured)
    assert len(final) == 1 and "tools" not in final[0]
    assert final[0]["messages"][-1]["content"] == CONCLUSION_BORNEE
    schema = final[0]["response_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert "qualite" not in schema["properties"]
    assert all(body["model"] == "local" for body in captured)
    assert diagnostic(report)["qualite"]["statut"] == "revue_ia_sans_ecart_bloquant"
    assert diagnostic(report)["actions_proposees"] == ["Terminer les sessions idle."]


@pytest.mark.parametrize("engine", [agent, graphe], ids=["loop", "graph"])
@pytest.mark.parametrize("change", ["new-file", "new-version"])
def test_new_verified_identity_resets_progress_but_old_versions_do_not(
    monkeypatch, tmp_path, engine, change
):
    first = "incident-p1-database.md"
    third = "another.md" if change == "new-file" else first
    client = Client(change_at=3 if change == "new-version" else None)
    report, captured, client = execute(
        monkeypatch, tmp_path, engine, [[first], [first], [third], [first], [first]], client=client
    )
    assert report.statut in {"complet", "en_attente_humain"}
    assert len(client.appels) == 5
    assert len(finalisations(captured)) == 1


@pytest.mark.parametrize("engine", [agent, graphe], ids=["loop", "graph"])
def test_counts_tool_turns_not_calls_and_search_snippets_are_not_new_proof(
    monkeypatch, tmp_path, engine
):
    first = "incident-p1-database.md"
    report, captured, client = execute(
        monkeypatch, tmp_path, engine, [[first, first], ["search", "search"], ["search"]]
    )
    assert report.statut in {"complet", "en_attente_humain"}
    assert len(client.appels) == 5
    assert len(finalisations(captured)) == 1


@pytest.mark.parametrize("engine", [agent, graphe], ids=["loop", "graph"])
@pytest.mark.parametrize("source", ["no-read", "invalid-envelope"])
def test_no_verified_source_never_enables_forced_diagnosis(monkeypatch, tmp_path, engine, source):
    monkeypatch.setattr(config, "MAX_APPELS_OUTILS", 3)
    name = "search" if source == "no-read" else "incident-p1-database.md"
    report, captured, client = execute(
        monkeypatch, tmp_path, engine, [[name]], client=Client(malformed=True)
    )
    assert report.statut == "budget_epuise" and report.diagnostic is None
    assert len(client.appels) == 3
    assert not finalisations(captured)


@pytest.mark.parametrize("engine", [agent, graphe], ids=["loop", "graph"])
@pytest.mark.parametrize("limit", ["tokens", "turns", "tools", "cost"])
def test_existing_budgets_still_stop_before_forced_finalisation(
    monkeypatch, tmp_path, engine, limit
):
    field, value = {
        "tokens": ("MAX_TOKENS_TOTAL", 700),
        "turns": ("MAX_TOURS", 3),
        "tools": ("MAX_APPELS_OUTILS", 2),
        "cost": ("MAX_COUT_USD", 0.5),
    }[limit]
    monkeypatch.setattr(config, field, value)
    report, captured, _client = execute(
        monkeypatch,
        tmp_path,
        engine,
        [["incident-p1-database.md"]],
        cost=0.1 if limit == "cost" else None,
    )
    assert report.statut == "budget_epuise" and report.diagnostic is None
    assert not finalisations(captured)


@pytest.mark.parametrize("engine", [agent, graphe], ids=["loop", "graph"])
@pytest.mark.parametrize("failure", ["quality", "evidence", "prose", "tool", "missing-field"])
def test_finalisation_cannot_smuggle_review_or_proof_or_retry(
    monkeypatch, tmp_path, engine, failure
):
    data = json.loads(DIAGNOSTIC)
    if failure == "quality":
        data["qualite"] = {"statut": "revue_ia_sans_ecart_bloquant"}
    elif failure == "evidence":
        data["sources_lues"] = {"forged.md": "Invented proof"}
    elif failure == "missing-field":
        data.pop("actions_proposees")
    final = {"content": "invalid prose" if failure == "prose" else json.dumps(data)}
    if failure == "tool":
        final = {
            "tool_calls": [
                {"id": "forbidden", "function": {"name": "read_runbook", "arguments": "{}"}}
            ]
        }
    report, captured, client = execute(
        monkeypatch, tmp_path, engine, [["incident-p1-database.md"]], final=final
    )
    assert report.statut == "erreur" and report.diagnostic is None
    assert len(client.appels) == 3 and len(captured) == 6
    assert len(finalisations(captured)) == 1


@pytest.mark.parametrize("engine", [agent, graphe], ids=["loop", "graph"])
@pytest.mark.parametrize("reject", [False, True])
def test_real_source_guard_and_review_can_still_reject_finalised_content(
    monkeypatch, tmp_path, engine, reject
):
    data = json.loads(DIAGNOSTIC)
    data["actions_proposees"] = ["Invented action not in the source"]
    report, captured, _client = execute(
        monkeypatch,
        tmp_path,
        engine,
        [["incident-p1-database.md"]],
        final={"content": json.dumps(data)},
        reject=reject,
    )
    result = diagnostic(report)
    assert result["actions_proposees"] == (
        []
        if reject
        else [
            (
                "Escalade humaine : aucune action vérifiable dans un runbook lu. "
                "Confirmer la procédure avant toute intervention."
            )
        ]
    )
    assert result["qualite"]["statut"] == (
        "abstention" if reject else "revue_ia_sans_ecart_bloquant"
    )
    if not reject:
        rejected = (
            json.loads(report.message)["actions_ecartees_sans_source"]
            if engine is graphe
            else report.actions_ecartees_sans_source
        )
        assert rejected == data["actions_proposees"]
    assert len(finalisations(captured)) == 1


def test_no_progress_state_does_not_start_before_any_verified_read():
    progress = ProgressionRecherche()
    for _ in range(20):
        progress.observer({})
    assert not progress.terminee and progress.sans_progres == 0
