"""La boucle de l'agent, écrite à la main.

Il n'y a pas de framework ici, et ce n'est pas un manque : la boucle
d'un agent outillé tient en une trentaine de lignes lisibles, et ce sont
exactement les lignes où se décident le budget, le cloisonnement et le
traitement des résultats d'outils. Les déléguer à une bibliothèque, c'est
déléguer les garde-fous.

Trois étapes, deux frontières de données :

  alerte brute ──[ local, CONFIDENTIEL ]──> extraction anonymisée
                                                │
                        ═══ frontière ═══       │  seule cette forme
                                                │  franchit la frontière
                 ──[ fast, DERIVE ]──> tri  ────┤
                 ──[ smart, DERIVE ]──> boucle outillée ──> diagnostic

L'étape de tri emploie l'alias `fast` comme prévu, mais sur l'extraction
et non sur l'alerte : le garde-fou de cloisonnement prime, et il n'y a
aucune raison de payer en confidentialité ce qu'on peut obtenir sur une
donnée dérivée.
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

# Le modèle local raisonne avant de répondre : le budget de sortie doit
# couvrir le raisonnement ET le JSON, sinon la réponse est tronquée.
MAX_TOKENS_LOCAL = 3_000
MAX_TOKENS_TRI = 600
MAX_TOKENS_RAISONNEMENT = 2_000


def analyser(alerte: str) -> Rapport:
    """Analyse une alerte et rend un rapport. Ne remédie jamais."""
    budget = Budget(
        max_appels_outils=config.MAX_APPELS_OUTILS,
        max_cout_usd=config.MAX_COUT_USD,
    )
    rapport = Rapport(statut="erreur")

    with tracage.tracer().start_as_current_span("task.incident_analysis") as span:
        span.set_attribute(tracage.ATTR_TYPE_TACHE, "incident_analysis")
        # La span parente porte la classification la plus stricte de
        # l'exécution : elle englobe le traitement de l'alerte brute.
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


# --- Étape 1 : extraction, sur donnée brute, en local ---------------------


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


# --- Étape 2 : tri, sur donnée dérivée ------------------------------------


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


# --- Étape 3 : boucle outillée --------------------------------------------


def _raisonner(
    extraction: Extraction,
    classification: ClassificationAlerte,
    client: ClientRunbooks,
    budget: Budget,
) -> tuple[Diagnostic, list[str]]:
    """Boucle appel / outil / résultat, sous double budget.

    La boucle s'arrête pour l'une de quatre raisons : le modèle rend son
    JSON, le budget d'outils est épuisé, le budget monétaire est dépassé,
    ou le plafond de tours est atteint. Aucune ne produit un demi-résultat
    présenté comme complet.
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
            # Les outils restent déclarés même à budget épuisé. Les
            # retirer ferait répondre le modèle sans les avoir consultés,
            # et cette réponse dégradée serait rendue comme un
            # diagnostic. Le budget doit être opposé au moment où
            # l'agent tente de le dépasser, pas contourné en amont.
            outils=declarations,
            max_tokens=MAX_TOKENS_RAISONNEMENT,
        )

        if reponse.appels_outils:
            messages.append(_message_assistant(reponse.message))
            for appel in reponse.appels_outils:
                nom, arguments = _decoder_appel(appel)
                # Lève BudgetEpuise si le plafond est atteint : l'outil
                # n'est alors jamais exécuté.
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
            # Une seule relance : le modèle a fini d'analyser mais a rendu
            # de la prose. On lui redemande la forme, pas le fond.
            relance_tentee = True
            messages.append(_message_assistant(reponse.message))
            messages.append({"role": "user", "content": prompts.RELANCE_FINALISATION})

    raise BudgetEpuise(
        "plafond de tours de boucle atteint",
        f"{config.MAX_TOURS} tours sans diagnostic",
    )


def _message_assistant(message: dict[str, Any]) -> dict[str, Any]:
    """Reconstruit un message assistant propre pour l'historique.

    La passerelle renvoie des champs spécifiques au fournisseur qui ne
    sont pas toujours acceptés en entrée. On ne réinjecte que ce que le
    protocole définit.
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
    """Extrait nom et arguments d'un appel d'outil.

    Les arguments arrivent en JSON sérialisé, produit par le modèle :
    ils peuvent être malformés. Un décodage raté ne doit pas interrompre
    l'analyse, il doit produire un appel qui échouera proprement côté
    outil, avec un message que le modèle peut corriger.
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
