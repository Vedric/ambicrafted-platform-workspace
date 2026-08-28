"""The agent loop, written by hand.

There is no framework here, and that is not something missing: the loop of
a tool-using agent fits in some thirty readable lines, and those are
exactly the lines where the budget, the compartmentalisation and the
handling of tool results are decided. Delegating them to a library means
delegating the guardrails.

Three steps, two data frontiers:

  raw alert ──[ local, CONFIDENTIEL ]──> anonymised extraction
                                                │
                      ═══ frontier ═══          │  only this form
                                                │  crosses the frontier
               ──[ fast, DERIVE ]──> triage ────┤
               ──[ smart, DERIVE ]──> tool loop ──> diagnosis

The triage step uses the `fast` alias as intended, but on the extraction
rather than on the alert: the compartmentalisation guardrail comes first,
and there is no reason to pay in confidentiality for what can be obtained
from derived data.
"""

from __future__ import annotations

import json
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from pydantic import ValidationError

from . import config, prompts, tracage
from .budget import Budget, BudgetEpuise
from .config import Classification
from .llm import ErreurPasserelle, FuiteConfidentielle, appeler_llm, extraire_json
from .modeles import (
    ClassificationAlerte,
    Diagnostic,
    Extraction,
    Rapport,
    appliquer_garde_source,
)
from .outils import ClientRunbooks, ErreurOutil, executer_outil

# The local model reasons before answering: the output budget has to cover
# the reasoning AND the JSON, otherwise the response comes back truncated.
MAX_TOKENS_LOCAL = 3_000
MAX_TOKENS_TRI = 600
MAX_TOKENS_RAISONNEMENT = 2_000


def analyser(alerte: str) -> Rapport:
    """Analyse an alert and return a report. Never remediates."""
    budget = Budget(
        max_appels_outils=config.MAX_APPELS_OUTILS,
        max_cout_usd=config.MAX_COUT_USD,
    )
    rapport = Rapport(statut="erreur")

    with tracage.tracer().start_as_current_span("task.incident_analysis") as span:
        span.set_attribute(tracage.ATTR_TYPE_TACHE, "incident_analysis")
        # The parent span carries the strictest classification of the run:
        # it encloses the handling of the raw alert.
        span.set_attribute(tracage.ATTR_CLASSIFICATION, Classification.CONFIDENTIEL.value)
        span.set_attribute(tracage.ATTR_BUDGET_MAX_OUTILS, budget.max_appels_outils)
        span.set_attribute(tracage.ATTR_BUDGET_MAX_COUT, budget.max_cout_usd)
        span.set_attribute("ambicrafted.alert.chars", len(alerte))

        contexte = span.get_span_context()
        rapport.trace_id = format(contexte.trace_id, "032x")

        try:
            rapport.extraction = _extraire(alerte, budget)
            rapport.injections_signalees = list(
                rapport.extraction.instructions_detectees
            )
            if rapport.injections_signalees:
                span.set_attribute("ambicrafted.prompt_injection.reported", True)
                span.set_attribute(
                    "ambicrafted.prompt_injection.count",
                    len(rapport.injections_signalees),
                )

            rapport.classification = _trier(rapport.extraction, budget)
            span.set_attribute("ambicrafted.alert.urgency", rapport.classification.urgence)
            span.set_attribute("ambicrafted.alert.known", rapport.classification.connue)

            with ClientRunbooks() as client:
                brut, outils = _raisonner(
                    rapport.extraction, rapport.classification, client, budget
                )
            rapport.outils_appeles = outils

            diagnostic, ecartees = appliquer_garde_source(brut)
            rapport.diagnostic = diagnostic
            rapport.actions_ecartees_sans_source = ecartees
            rapport.statut = "complet"
            span.set_attribute("ambicrafted.diagnostic.confidence", diagnostic.confiance.value)
            span.set_attribute(
                "ambicrafted.diagnostic.sourced", diagnostic.runbook_source is not None
            )
            if ecartees:
                span.set_attribute("ambicrafted.actions.rejected_unsourced", len(ecartees))

        except BudgetEpuise as e:
            rapport.statut = "budget_epuise"
            rapport.message = str(e)
            span.set_attribute(tracage.ATTR_VERDICT, "budget_exhausted")
            span.set_status(Status(StatusCode.ERROR, str(e)))

        except (FuiteConfidentielle, ErreurPasserelle, ErreurOutil, ValidationError) as e:
            rapport.statut = "erreur"
            rapport.message = f"{type(e).__name__} : {e}"
            span.set_attribute(tracage.ATTR_VERDICT, "error")
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)

        rapport.budget = budget.resume()
        span.set_attribute(tracage.ATTR_COUT, round(budget.cout_usd, 6))
        span.set_attribute(tracage.ATTR_BUDGET_OUTILS, budget.appels_outils)
        if rapport.statut == "complet":
            span.set_attribute(tracage.ATTR_VERDICT, "complete")

    tracage.vider()
    return rapport


# --- Step 1: extraction, over raw data, locally ---------------------------


def _extraire(alerte: str, budget: Budget) -> Extraction:
    reponse = appeler_llm(
        alias=config.ALIAS_EXTRACTION,
        messages=prompts.messages_extraction(alerte),
        classification=Classification.CONFIDENTIEL,
        budget=budget,
        tache="extraction",
        max_tokens=MAX_TOKENS_LOCAL,
    )
    return Extraction.model_validate(extraire_json(reponse.contenu))


# --- Step 2: triage, over derived data ------------------------------------


def _trier(extraction: Extraction, budget: Budget) -> ClassificationAlerte:
    reponse = appeler_llm(
        alias="fast",
        messages=prompts.messages_classification(extraction),
        classification=Classification.DERIVE,
        budget=budget,
        tache="classification",
        max_tokens=MAX_TOKENS_TRI,
    )
    return ClassificationAlerte.model_validate(extraire_json(reponse.contenu))


# --- Step 3: the tool loop ------------------------------------------------


def _raisonner(
    extraction: Extraction,
    classification: ClassificationAlerte,
    client: ClientRunbooks,
    budget: Budget,
) -> tuple[Diagnostic, list[str]]:
    """Call / tool / result loop, under a double budget.

    The loop stops for one of four reasons: the model returns its JSON, the
    tool budget is exhausted, the monetary budget is exceeded, or the turn
    ceiling is reached. None of them yields a half-result presented as
    complete.
    """
    messages = prompts.messages_raisonnement(extraction, classification)
    declarations = client.outils_openai()
    appeles: list[str] = []
    relance_tentee = False

    for tour in range(config.MAX_TOURS):
        reponse = appeler_llm(
            alias=config.ALIAS_RAISONNEMENT,
            messages=messages,
            classification=Classification.DERIVE,
            budget=budget,
            tache="raisonnement",
            # The tools stay declared even once the budget is spent.
            # Removing them would make the model answer without having
            # consulted them, and that degraded answer would be returned
            # as a diagnosis. The budget must be held against the agent at
            # the moment it tries to exceed it, not dodged beforehand.
            outils=declarations,
            max_tokens=MAX_TOKENS_RAISONNEMENT,
        )

        if reponse.appels_outils:
            messages.append(_message_assistant(reponse.message))
            for appel in reponse.appels_outils:
                nom, arguments = _decoder_appel(appel)
                # Raises BudgetEpuise if the ceiling is reached: the tool
                # is then never run.
                resultat = executer_outil(client, nom, arguments, budget)
                appeles.append(nom)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": appel.get("id", ""),
                        "content": prompts.message_resultat_outil(nom, resultat),
                    }
                )
            continue

        try:
            return Diagnostic.model_validate(extraire_json(reponse.contenu)), appeles
        except (ErreurPasserelle, ValidationError) as e:
            if relance_tentee:
                raise ErreurPasserelle(
                    f"Le modèle n'a pas produit de diagnostic exploitable après "
                    f"relance : {e}"
                ) from e
            # One retry only: the model has finished analysing but
            # returned prose. We ask again for the shape, not the content.
            relance_tentee = True
            messages.append(_message_assistant(reponse.message))
            messages.append({"role": "user", "content": prompts.RELANCE_FINALISATION})

    raise BudgetEpuise(
        "plafond de tours de boucle atteint",
        f"{config.MAX_TOURS} tours sans diagnostic",
    )


def _message_assistant(message: dict[str, Any]) -> dict[str, Any]:
    """Rebuild a clean assistant message for the history.

    The gateway returns provider-specific fields that are not always
    accepted back as input. Only what the protocol defines is fed back in.
    """
    propre: dict[str, Any] = {"role": "assistant"}
    if message.get("content"):
        propre["content"] = message["content"]
    if message.get("tool_calls"):
        propre["tool_calls"] = message["tool_calls"]
    if "content" not in propre and "tool_calls" not in propre:
        propre["content"] = ""
    return propre


def _decoder_appel(appel: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Extract the name and arguments of a tool call.

    The arguments arrive as serialised JSON produced by the model, so they
    may be malformed. A failed decode must not interrupt the analysis; it
    must produce a call that fails cleanly on the tool side, with a message
    the model can act on.
    """
    fonction = appel.get("function") or {}
    nom = str(fonction.get("name") or "")
    brut = fonction.get("arguments") or "{}"
    if isinstance(brut, dict):
        return nom, brut
    try:
        arguments = json.loads(brut)
    except json.JSONDecodeError:
        return nom, {}
    return nom, arguments if isinstance(arguments, dict) else {}


def id_trace_courante() -> str | None:
    contexte = trace.get_current_span().get_span_context()
    return format(contexte.trace_id, "032x") if contexte.is_valid else None
