"""La même analyse, orchestrée par un graphe d'états.

Ce module est le pendant de `agent.py`, pas son remplaçant. Les deux
produisent un `Rapport` identique en s'appuyant sur exactement les mêmes
garde-fous : `llm.appeler_llm`, `outils.executer_outil`, `prompts.bloc`,
`budget.Budget`, `modeles.appliquer_garde_source`. Aucun de ces cinq
modules n'est modifié ni contourné ici — c'est la condition pour que la
comparaison de l'ADR 0004 porte sur l'orchestration et sur rien d'autre.

Ce que le graphe ajoute, et que la boucle maison ne sait pas faire :

  extraction ─> classification ─> raisonnement <──┐
                                       │          │
                                       ├──> recherche_runbooks
                                       │
                                       ├──> diagnostic ──> porte_humaine ──> FIN
                                       │         └── relance ──┘
                                       └──> abandon ──> FIN

`porte_humaine` appelle `interrupt()` : le graphe écrit son état complet
dans SQLite et rend la main AVANT de livrer le diagnostic. Le processus
peut mourir. Une reprise ultérieure sur le même `thread_id`, avec
`Command(resume=...)`, repart exactement de là, contexte intact.

Deux différences de comportement assumées vis-à-vis d'`agent.py`, l'une
et l'autre plus strictes, documentées dans l'ADR 0004 :

1. Le budget d'outils est opposé par une arête conditionnelle, donc
   AVANT d'entrer dans le nœud. Une salve de trois outils demandée quand
   il n'en reste que deux est refusée en bloc ; la boucle maison en
   aurait exécuté deux puis levé. Les deux s'arrêtent sans demi-résultat.
2. La relance de finalisation est une arête, pas un `except` : elle est
   visible dans la trace et dans le journal d'état.
"""

from __future__ import annotations

import contextlib
import functools
import json
import operator
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from opentelemetry import trace
from opentelemetry.trace import Link, NonRecordingSpan, SpanContext, Status, StatusCode, TraceFlags
from pydantic import ValidationError

from . import config, prompts, tracage
from .agent import (
    MAX_TOKENS_LOCAL,
    MAX_TOKENS_RAISONNEMENT,
    MAX_TOKENS_TRI,
    _decoder_appel,
    _message_assistant,
)
from .budget import Budget, BudgetEpuise
from .config import Classification
from .llm import ErreurPasserelle, FuiteConfidentielle, appeler_llm, extraire_json
from .modeles import (
    ClassificationAlerte,
    Confiance,
    Diagnostic,
    Extraction,
    Rapport,
    appliquer_garde_source,
)
from .outils import ClientRunbooks, ErreurOutil, executer_outil

# Les plafonds de tokens et les deux fonctions de décodage viennent
# d'`agent.py`. Les recopier ici donnerait deux réglages qui divergent
# à la première retouche, et la comparaison mesurerait cette divergence
# au lieu de mesurer l'orchestration.

CHEMIN_CHECKPOINTS = os.environ.get(
    "SRE_CHECKPOINT_DB",
    os.path.expanduser("~/.local/state/sre-agent/graphe.sqlite"),
)

# Rétention des fils, en jours. 14 : la durée pendant laquelle Tempo garde
# les traces (block_retention, 336 h) — un fil et sa trace expirent
# ensemble — et une rotation d'astreinte. Voir ADR 0004, Conséquences.
RETENTION_JOURS = int(os.environ.get("SRE_RETENTION_JOURS", "14"))


# --- État -----------------------------------------------------------------


class EtatSRE(TypedDict, total=False):
    """L'état partagé, typé, et surtout : sérialisable.

    Tout ce qui doit survivre à la mort du processus est ici. Ce qui n'y
    est pas — la session MCP, le client HTTP — est une ressource de
    processus, rétablie à la reprise.

    Les champs annotés d'`operator.add` sont des accumulateurs : deux
    nœuds qui écrivent dans le même super-pas concatènent leurs
    contributions au lieu que le dernier écrase le premier. C'est la
    raison technique d'être du reducer, et elle vaut aussi pour un
    graphe séquentiel comme celui-ci : le cycle
    raisonnement -> recherche_runbooks -> raisonnement écrit dans
    `messages` à chaque tour, et une sémantique d'écrasement perdrait
    l'historique de l'outillage à chaque passage.
    """

    alerte: str

    extraction: Extraction | None
    classification: ClassificationAlerte | None
    diagnostic: Diagnostic | None

    # --- Accumulateurs ---------------------------------------------------
    messages: Annotated[list[dict[str, Any]], operator.add]
    outils_appeles: Annotated[list[str], operator.add]
    injections_signalees: Annotated[list[str], operator.add]
    actions_ecartees_sans_source: Annotated[list[str], operator.add]
    journal: Annotated[list[str], operator.add]
    # Le budget n'est PAS stocké comme un total, mais comme la suite de
    # ses consommations. Un total serait écrasé par la dernière branche à
    # écrire ; une liste de deltas s'additionne. Le compteur est ensuite
    # rejoué par `_budget()`, ce qui le rend aussi juste après une reprise
    # qu'avant l'interruption.
    depenses: Annotated[list[dict[str, float]], operator.add]

    # --- Contrôle --------------------------------------------------------
    tours: int
    relance_tentee: bool
    motif_abandon: str
    statut: str
    message: str
    approbation: dict[str, Any] | None
    trace_id: str | None
    trace_origine: dict[str, str] | None


_CHAMPS_BUDGET = (
    "appels_outils",
    "appels_llm",
    "cout_usd",
    "tokens_entree",
    "tokens_sortie",
)


def _budget(etat: EtatSRE) -> Budget:
    """Rejoue les consommations enregistrées pour reconstituer le budget.

    Les compteurs sont réaffectés directement plutôt que rejoués par
    `consommer_llm`, qui lèverait au milieu du rejeu. Ce n'est pas un
    contournement du garde-fou : les plafonds restent ceux de `config`,
    et c'est bien `Budget` qui les oppose au prochain appel réel. La
    sémantique d'`agent.py` est conservée — un dépassement est constaté
    après coup et interrompt l'étape suivante.
    """
    budget = Budget(
        max_appels_outils=config.MAX_APPELS_OUTILS,
        max_cout_usd=config.MAX_COUT_USD,
    )
    for depense in etat.get("depenses") or []:
        for champ in _CHAMPS_BUDGET:
            setattr(budget, champ, getattr(budget, champ) + depense.get(champ, 0))
    return budget


def _instantane(budget: Budget) -> dict[str, float]:
    return {champ: getattr(budget, champ) for champ in _CHAMPS_BUDGET}


def _delta(avant: dict[str, float], budget: Budget) -> dict[str, float]:
    return {champ: getattr(budget, champ) - avant[champ] for champ in _CHAMPS_BUDGET}


# --- Contexte de traçage et session d'outils ------------------------------
#
# Deux ressources ne peuvent pas vivre dans l'état sérialisé : la span
# parente et le sous-processus MCP. Elles sont donc portées par le
# processus, installées par `_execution()` et lues par les nœuds. Une
# exécution de graphe par processus, ce qui est le mode d'emploi du CLI.

_contexte_parent: Any = None
_pile_ressources: contextlib.ExitStack | None = None
_client_runbooks: ClientRunbooks | None = None


def _client() -> ClientRunbooks:
    """Ouvre la session MCP à la première demande, jamais avant.

    Une reprise après approbation n'appelle plus d'outil : payer le
    démarrage du sous-processus serait payer pour rien.
    """
    global _client_runbooks
    if _client_runbooks is None:
        if _pile_ressources is None:
            raise ErreurOutil("Nœud d'outils exécuté hors d'une exécution de graphe.")
        _client_runbooks = _pile_ressources.enter_context(ClientRunbooks())
    return _client_runbooks


def noeud(nom: str):
    """Enveloppe un nœud : une span enfant, et les erreurs mises en état.

    C'est ici que se joue le point 3 du portage. Un nœud ne décide jamais
    de la suite : il fait son travail, ou il consigne pourquoi il n'a pas
    pu, et rend la main. Le routage est l'affaire des arêtes.

    La dépense est calculée par différence avant/après, y compris quand
    le nœud échoue : un appel payé puis rejeté reste payé, et le rapport
    doit le dire.
    """

    def decorateur(fonction):
        @functools.wraps(fonction)
        def enveloppe(etat: EtatSRE) -> dict[str, Any]:
            budget = _budget(etat)
            avant = _instantane(budget)
            with tracage.tracer().start_as_current_span(
                f"node.{nom}", context=_contexte_parent
            ) as span:
                span.set_attribute(tracage.ATTR_TYPE_TACHE, "graph_node")
                span.set_attribute("ambicrafted.graph.node", nom)
                span.set_attribute("ambicrafted.graph.turn", etat.get("tours", 0))
                try:
                    maj: dict[str, Any] = fonction(etat, budget) or {}
                except BudgetEpuise as e:
                    maj = {"motif_abandon": str(e)}
                    span.set_attribute(tracage.ATTR_VERDICT, "budget_exhausted")
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                except (
                    FuiteConfidentielle,
                    ErreurPasserelle,
                    ErreurOutil,
                    ValidationError,
                ) as e:
                    maj = {"statut": "erreur", "message": f"{type(e).__name__} : {e}"}
                    span.set_attribute(tracage.ATTR_VERDICT, "error")
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)

                depense = _delta(avant, budget)
                if any(depense.values()):
                    maj["depenses"] = [*maj.get("depenses", []), depense]
                maj["journal"] = [*maj.get("journal", []), nom]
                span.set_attribute(tracage.ATTR_COUT, round(budget.cout_usd, 6))
                span.set_attribute(tracage.ATTR_BUDGET_OUTILS, budget.appels_outils)
                return maj

        return enveloppe

    return decorateur


# --- Nœuds ----------------------------------------------------------------


@noeud("extraction")
def extraction(etat: EtatSRE, budget: Budget) -> dict[str, Any]:
    """Alerte brute -> forme anonymisée. Local, classé CONFIDENTIEL.

    Seul nœud du graphe à voir la donnée client. Le cloisonnement n'est
    pas garanti par sa position dans le graphe mais par la classification
    passée à `appeler_llm`, qui refuserait un alias frontière.
    """
    reponse = appeler_llm(
        alias=config.ALIAS_EXTRACTION,
        messages=prompts.messages_extraction(etat["alerte"]),
        classification=Classification.CONFIDENTIEL,
        budget=budget,
        tache="extraction",
        max_tokens=MAX_TOKENS_LOCAL,
    )
    extrait = Extraction.model_validate(extraire_json(reponse.contenu))
    return {
        "extraction": extrait,
        "injections_signalees": list(extrait.instructions_detectees),
    }


@noeud("classification")
def classification(etat: EtatSRE, budget: Budget) -> dict[str, Any]:
    """Tri sur donnée dérivée, alias `fast`. Amorce aussi le raisonnement.

    Le nœud sème `messages` avec le prompt système et la charge : les
    tours suivants n'y ajouteront que des messages, jamais ne le
    remplaceront, grâce au reducer.
    """
    extrait = etat["extraction"]
    reponse = appeler_llm(
        alias="fast",
        messages=prompts.messages_classification(extrait),
        classification=Classification.DERIVE,
        budget=budget,
        tache="classification",
        max_tokens=MAX_TOKENS_TRI,
    )
    tri = ClassificationAlerte.model_validate(extraire_json(reponse.contenu))
    return {
        "classification": tri,
        "messages": prompts.messages_raisonnement(extrait, tri),
    }


@noeud("raisonnement")
def raisonnement(etat: EtatSRE, budget: Budget) -> dict[str, Any]:
    """Un tour de modèle outillé. Un seul : le cycle est dans le graphe.

    Les outils restent déclarés même à budget épuisé, exactement comme
    dans `agent.py` : les retirer ferait répondre le modèle sans avoir
    consulté les runbooks, et cette réponse dégradée serait rendue comme
    un diagnostic.
    """
    reponse = appeler_llm(
        alias=config.ALIAS_RAISONNEMENT,
        messages=etat["messages"],
        classification=Classification.DERIVE,
        budget=budget,
        tache="raisonnement",
        outils=_client().outils_openai(),
        max_tokens=MAX_TOKENS_RAISONNEMENT,
    )
    return {
        "messages": [_message_assistant(reponse.message)],
        "tours": etat.get("tours", 0) + 1,
    }


@noeud("recherche_runbooks")
def recherche_runbooks(etat: EtatSRE, budget: Budget) -> dict[str, Any]:
    """Exécute les outils MCP demandés au tour précédent.

    `executer_outil` décompte le budget avant d'appeler le serveur et
    lève si le plafond est atteint. L'arête d'entrée a normalement déjà
    écarté ce cas ; le garde-fou reste en place et fait foi.
    """
    demandes = _appels_outils(etat["messages"][-1])
    messages: list[dict[str, Any]] = []
    noms: list[str] = []
    for appel in demandes:
        nom, arguments = _decoder_appel(appel)
        resultat = executer_outil(_client(), nom, arguments, budget)
        noms.append(nom)
        messages.append(
            {
                "role": "tool",
                "tool_call_id": appel.get("id", ""),
                "content": prompts.message_resultat_outil(nom, resultat),
            }
        )
    return {"messages": messages, "outils_appeles": noms}


@noeud("diagnostic")
def diagnostic(etat: EtatSRE, budget: Budget) -> dict[str, Any]:
    """Valide le JSON final et applique la garde de source.

    En cas de prose, le nœud ne relance pas lui-même : il pose la
    demande de relance dans l'état, et l'arête décide de repasser par
    `raisonnement`. La différence n'est pas cosmétique — la relance
    devient un franchissement d'arête observable, au lieu d'un `except`
    invisible depuis l'extérieur.
    """
    contenu = etat["messages"][-1].get("content") or ""
    try:
        brut = Diagnostic.model_validate(extraire_json(contenu))
    except (ErreurPasserelle, ValidationError) as e:
        if etat.get("relance_tentee"):
            raise ErreurPasserelle(
                f"Le modèle n'a pas produit de diagnostic exploitable après "
                f"relance : {e}"
            ) from e
        return {
            "relance_tentee": True,
            "messages": [{"role": "user", "content": prompts.RELANCE_FINALISATION}],
        }

    retenu, ecartees = appliquer_garde_source(brut)
    return {"diagnostic": retenu, "actions_ecartees_sans_source": ecartees}


@noeud("porte_humaine")
def porte_humaine(etat: EtatSRE, budget: Budget) -> dict[str, Any]:
    """Le nœud qui justifie le portage : pause durable avant livraison.

    `interrupt()` lève une exception de contrôle que LangGraph
    intercepte après avoir écrit l'état dans le checkpointer. Ce qui est
    livré n'a donc jamais été livré sans qu'un humain l'ait vu, et cette
    propriété tient même si la machine s'arrête pendant la pause.

    La span est fermée sans erreur : une pause attendue n'est pas un
    incident, et la marquer en rouge rendrait le tableau de bord
    illisible le jour où la porte sert vraiment.
    """
    d = etat["diagnostic"]
    decision = interrupt(
        {
            "demande": "Approuver la livraison de ce diagnostic ?",
            "cause_probable": d.cause_probable,
            "confiance": d.confiance.value,
            "runbook_source": d.runbook_source,
            "actions_proposees": d.actions_proposees,
            "actions_ecartees_sans_source": etat.get("actions_ecartees_sans_source", []),
            "outils_appeles": etat.get("outils_appeles", []),
            "budget": _budget(etat).resume(),
            "reponse_attendue": "oui | non | texte libre",
        }
    )

    approbation = _lire_decision(decision)
    return {
        "approbation": approbation,
        "statut": "complet" if approbation["approuve"] else "rejete_par_humain",
        "message": "" if approbation["approuve"] else approbation["commentaire"],
    }


@noeud("abandon")
def abandon(etat: EtatSRE, budget: Budget) -> dict[str, Any]:
    """Sortie propre. Aucun diagnostic partiel n'est présenté comme complet.

    Le nœud rejoue les conditions de routage pour dire lequel des trois
    plafonds a mordu. Ce n'est pas de la cosmétique : « plafond d'outils »
    et « plafond de tours » appellent des corrections opposées, et à
    3 h du matin personne n'ira relire le graphe pour trancher.
    """
    if etat.get("statut") == "erreur":
        return {}
    return {
        "statut": "budget_epuise",
        "message": _motif_abandon(etat, budget),
        "diagnostic": None,
    }


def _motif_abandon(etat: EtatSRE, budget: Budget) -> str:
    """Attribue l'arrêt au plafond qui l'a réellement provoqué."""
    if motif := etat.get("motif_abandon"):
        return motif
    if budget.cout_usd >= config.MAX_COUT_USD:
        return str(
            BudgetEpuise(
                "plafond monétaire atteint",
                f"{budget.cout_usd:.4f}/{budget.max_cout_usd:.2f} USD "
                f"après {budget.appels_llm} appels LLM",
            )
        )
    demandes = _appels_outils((etat.get("messages") or [{}])[-1])
    if demandes and len(demandes) > budget.outils_restants():
        return str(
            BudgetEpuise(
                "plafond d'appels d'outils atteint",
                f"{budget.appels_outils}/{budget.max_appels_outils}, refus d'une "
                f"salve de {len(demandes)} outil(s) : "
                + ", ".join(sorted({_decoder_appel(a)[0] for a in demandes})),
            )
        )
    if etat.get("tours", 0) >= config.MAX_TOURS:
        return str(
            BudgetEpuise(
                "plafond de tours de boucle atteint",
                f"{config.MAX_TOURS} tours sans diagnostic",
            )
        )
    return str(BudgetEpuise("arrêt sur budget", "condition de sortie non attribuée"))


# --- Arêtes conditionnelles -----------------------------------------------
#
# Toute la logique de sortie est ici, en clair, dans des fonctions pures
# qui lisent l'état et rendent un nom de nœud. C'est le point 3 du
# portage : un dépassement de budget est une bifurcation du graphe, pas
# un `if` au milieu d'une boucle.


def _sortie_forcee(etat: EtatSRE) -> str | None:
    if etat.get("motif_abandon") or etat.get("statut") == "erreur":
        return "abandon"
    return None


def _budget_epuise(etat: EtatSRE) -> bool:
    return _budget(etat).cout_usd >= config.MAX_COUT_USD


def apres_extraction(etat: EtatSRE) -> str:
    return _sortie_forcee(etat) or (
        "abandon" if _budget_epuise(etat) else "classification"
    )


def apres_classification(etat: EtatSRE) -> str:
    return _sortie_forcee(etat) or (
        "abandon" if _budget_epuise(etat) else "raisonnement"
    )


def apres_raisonnement(etat: EtatSRE) -> str:
    """Outils, diagnostic ou abandon. Décidé sur l'état, pas dans le nœud."""
    if forcee := _sortie_forcee(etat):
        return forcee
    if etat.get("tours", 0) >= config.MAX_TOURS:
        return "abandon"

    demandes = _appels_outils(etat["messages"][-1])
    if not demandes:
        return "diagnostic"
    # Le budget est opposé avant l'entrée dans le nœud : une salve plus
    # large que ce qu'il reste est refusée en bloc, pas exécutée à moitié.
    if len(demandes) > _budget(etat).outils_restants():
        return "abandon"
    return "recherche_runbooks"


def apres_outils(etat: EtatSRE) -> str:
    return _sortie_forcee(etat) or (
        "abandon" if _budget_epuise(etat) else "raisonnement"
    )


def apres_diagnostic(etat: EtatSRE) -> str:
    if forcee := _sortie_forcee(etat):
        return forcee
    if etat.get("diagnostic") is None:
        # Relance demandée : le modèle a rendu de la prose. Une seule
        # fois, `relance_tentee` en fait foi côté nœud.
        return "abandon" if _budget_epuise(etat) else "raisonnement"
    return "porte_humaine"


# --- Assemblage -----------------------------------------------------------


def construire() -> StateGraph:
    graphe = StateGraph(EtatSRE)

    graphe.add_node("extraction", extraction)
    graphe.add_node("classification", classification)
    graphe.add_node("raisonnement", raisonnement)
    graphe.add_node("recherche_runbooks", recherche_runbooks)
    graphe.add_node("diagnostic", diagnostic)
    graphe.add_node("porte_humaine", porte_humaine)
    graphe.add_node("abandon", abandon)

    graphe.add_edge(START, "extraction")
    graphe.add_conditional_edges(
        "extraction", apres_extraction, ["classification", "abandon"]
    )
    graphe.add_conditional_edges(
        "classification", apres_classification, ["raisonnement", "abandon"]
    )
    graphe.add_conditional_edges(
        "raisonnement",
        apres_raisonnement,
        ["recherche_runbooks", "diagnostic", "abandon"],
    )
    graphe.add_conditional_edges(
        "recherche_runbooks", apres_outils, ["raisonnement", "abandon"]
    )
    graphe.add_conditional_edges(
        "diagnostic", apres_diagnostic, ["porte_humaine", "raisonnement", "abandon"]
    )
    graphe.add_edge("porte_humaine", END)
    graphe.add_edge("abandon", END)
    return graphe


# Le checkpointer est une frontière de confiance que la boucle maison
# n'avait pas : un fichier persistant que le graphe relit et désérialise.
# Par défaut, LangGraph y accepte n'importe quel type Python, ce que sa
# propre documentation signale comme un vecteur d'exécution de code pour
# qui sait écrire dans ce fichier. On lui oppose donc la même figure que
# `OUTILS_AUTORISES` : une liste blanche fermée, tenue par ce dépôt.
TYPES_PERSISTABLES = (Extraction, ClassificationAlerte, Diagnostic, Confiance)


def _serialiseur() -> JsonPlusSerializer:
    return JsonPlusSerializer(
        pickle_fallback=False,
        allowed_msgpack_modules=TYPES_PERSISTABLES,
    )


def compiler(chemin_db: str = CHEMIN_CHECKPOINTS):
    """Compile le graphe sur un checkpointer SQLite.

    SQLite et non Postgres : la persistance de l'agent ne doit pas
    dépendre de la base de la passerelle. Un agent qui tombe parce que
    la comptabilité de la passerelle est en maintenance serait un
    couplage gratuit entre deux préoccupations sans rapport. La voie
    d'évolution est documentée dans l'ADR 0004.

    Le fichier est créé en 0600 : il contient l'extraction de l'alerte,
    donc de la donnée dérivée d'une donnée client, et il survit au
    processus. Un état persistant lisible par tout le système annulerait
    une partie du bénéfice du cloisonnement.
    """
    dossier = os.path.dirname(os.path.abspath(chemin_db)) or "."
    os.makedirs(dossier, mode=0o700, exist_ok=True)
    connexion = sqlite3.connect(chemin_db, check_same_thread=False)
    with contextlib.suppress(OSError):
        # Le dossier autant que le fichier : SQLite crée à côté un -wal et
        # un -shm qui portent les mêmes données.
        os.chmod(dossier, 0o700)
        os.chmod(chemin_db, 0o600)
    return construire().compile(
        checkpointer=SqliteSaver(connexion, serde=_serialiseur())
    )


# --- Exécution ------------------------------------------------------------


@contextlib.contextmanager
def _execution(trace_origine: dict[str, str] | None):
    """Installe span parente et session d'outils pour la durée d'un invoke.

    Une reprise après interruption ouvre forcément une nouvelle trace :
    l'ancienne est morte avec le processus. Plutôt que de faire semblant,
    on relie explicitement la nouvelle à l'ancienne par un Link OTel, et
    Grafana affiche les deux moitiés d'une même histoire.
    """
    global _contexte_parent, _pile_ressources, _client_runbooks

    liens = []
    if trace_origine:
        with contextlib.suppress(ValueError, KeyError, TypeError):
            liens.append(
                Link(
                    SpanContext(
                        trace_id=int(trace_origine["trace_id"], 16),
                        span_id=int(trace_origine["span_id"], 16),
                        is_remote=True,
                        trace_flags=TraceFlags(TraceFlags.SAMPLED),
                    )
                )
            )

    with contextlib.ExitStack() as pile:
        _pile_ressources = pile
        _client_runbooks = None
        span = pile.enter_context(
            tracage.tracer().start_as_current_span(
                "task.incident_analysis", links=liens
            )
        )
        span.set_attribute(tracage.ATTR_TYPE_TACHE, "incident_analysis")
        span.set_attribute(tracage.ATTR_CLASSIFICATION, Classification.CONFIDENTIEL.value)
        span.set_attribute("ambicrafted.orchestration", "langgraph")
        span.set_attribute(tracage.ATTR_BUDGET_MAX_OUTILS, config.MAX_APPELS_OUTILS)
        span.set_attribute(tracage.ATTR_BUDGET_MAX_COUT, config.MAX_COUT_USD)
        if trace_origine:
            span.set_attribute("ambicrafted.resume.of_trace_id", trace_origine["trace_id"])

        contexte = span.get_span_context()
        _contexte_parent = trace.set_span_in_context(NonRecordingSpan(contexte))
        try:
            yield span, format(contexte.trace_id, "032x"), {
                "trace_id": format(contexte.trace_id, "032x"),
                "span_id": format(contexte.span_id, "016x"),
            }
        finally:
            _contexte_parent = None
            _pile_ressources = None
            _client_runbooks = None


def demarrer(alerte: str, thread_id: str, chemin_db: str = CHEMIN_CHECKPOINTS) -> Rapport:
    """Lance une analyse. S'arrête sur la porte humaine."""
    application = compiler(chemin_db)
    configuration = {"configurable": {"thread_id": thread_id}}
    with _execution(None) as (span, id_trace, origine):
        etat_initial: EtatSRE = {
            "alerte": alerte,
            "statut": "en_cours",
            "trace_id": id_trace,
            "trace_origine": origine,
        }
        resultat = application.invoke(etat_initial, configuration)
        return _finaliser(span, resultat, id_trace)


def reprendre(
    decision: str, thread_id: str, chemin_db: str = CHEMIN_CHECKPOINTS
) -> Rapport:
    """Reprend une analyse en pause, sur le même thread_id.

    Aucun argument d'alerte : tout ce qui est nécessaire est déjà dans
    le checkpoint. C'est précisément la démonstration.
    """
    from langgraph.types import Command

    application = compiler(chemin_db)
    configuration = {"configurable": {"thread_id": thread_id}}
    instantane = application.get_state(configuration)
    if not instantane.created_at:
        raise ErreurPasserelle(
            f"Aucun état enregistré pour le thread {thread_id!r} dans {chemin_db}."
        )
    origine = instantane.values.get("trace_origine")

    with _execution(origine) as (span, id_trace, _):
        resultat = application.invoke(Command(resume=decision), configuration)
        return _finaliser(span, resultat, origine.get("trace_id") if origine else id_trace)


def etat(thread_id: str, chemin_db: str = CHEMIN_CHECKPOINTS) -> dict[str, Any]:
    """Lit l'état persistant sans rien exécuter."""
    instantane = compiler(chemin_db).get_state({"configurable": {"thread_id": thread_id}})
    interruptions = [
        i.value for i in (getattr(instantane, "interrupts", None) or ())
    ]
    return {
        "thread_id": thread_id,
        "existe": bool(instantane.created_at),
        "prochains_noeuds": list(instantane.next),
        "journal": instantane.values.get("journal", []),
        "en_attente": interruptions,
        "valeurs": instantane.values,
    }


def purger(
    avant_jours: int = RETENTION_JOURS,
    chemin_db: str = CHEMIN_CHECKPOINTS,
    *,
    simulation: bool = False,
    maintenant: datetime | None = None,
) -> dict[str, Any]:
    """Supprime les fils sans activité depuis plus de `avant_jours` jours.

    L'âge d'un fil est celui de son dernier checkpoint, tel que le
    checkpointer l'a horodaté (`created_at`, la même source que `etat`).
    Un fil en pause sur la porte humaine vieillit comme les autres et
    est purgé comme les autres : une approbation qui n'est pas venue en
    deux semaines ne viendra plus, l'alerte a été traitée autrement. Le
    bilan le signale (`en_pause`) pour que l'opérateur le voie.

    Supprimer les lignes ne suffit pas : SQLite garde les pages libérées
    dans le fichier, et le journal WAL en porte une copie. D'où VACUUM
    puis troncature du WAL, sans quoi la donnée dérivée d'alerte survit
    à sa « purge ».
    """
    if avant_jours < 0:
        raise ValueError("avant_jours doit être positif ou nul.")
    maintenant = maintenant or datetime.now(UTC)
    seuil = maintenant - timedelta(days=avant_jours)
    bilan: dict[str, Any] = {
        "fichier": chemin_db,
        "seuil": seuil.isoformat(),
        "simulation": simulation,
        "purges": [],
        "conserves": 0,
        "octets_avant": 0,
        "octets_apres": 0,
    }
    if not os.path.exists(chemin_db):
        return bilan  # rien à purger, et surtout ne pas créer le fichier

    bilan["octets_avant"] = _empreinte(chemin_db)
    application = compiler(chemin_db)
    checkpointer = application.checkpointer
    checkpointer.setup()
    connexion = checkpointer.conn
    fils = [
        fil
        for (fil,) in connexion.execute(
            "SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id"
        )
    ]
    for fil in fils:
        instantane = application.get_state({"configurable": {"thread_id": fil}})
        derniere = (
            datetime.fromisoformat(instantane.created_at) if instantane.created_at else None
        )
        if derniere is not None and derniere >= seuil:
            bilan["conserves"] += 1
            continue
        bilan["purges"].append(
            {
                "thread_id": fil,
                "derniere_activite": derniere.isoformat() if derniere else None,
                "en_pause": bool(instantane.next),
            }
        )
        if not simulation:
            checkpointer.delete_thread(fil)

    if not simulation and bilan["purges"]:
        connexion.execute("VACUUM")
        connexion.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    connexion.close()
    bilan["octets_apres"] = _empreinte(chemin_db)
    return bilan


def _empreinte(chemin_db: str) -> int:
    """Octets réellement occupés : le fichier et son journal WAL.

    En mode WAL, le fichier principal peut ne faire qu'une page alors que
    tout l'état vit dans `-wal` ; mesurer l'un sans l'autre ment.
    """
    return sum(
        os.path.getsize(c) for c in (chemin_db, chemin_db + "-wal") if os.path.exists(c)
    )


def _finaliser(span: Any, resultat: dict[str, Any], id_trace: str | None) -> Rapport:
    """Assemble le Rapport, le même objet que celui d'`agent.py`.

    Le contrat de sortie ne change pas d'une implémentation à l'autre :
    c'est ce qui permet de réutiliser le rendu du CLI, et surtout ce qui
    interdit de maquiller une différence d'orchestration en différence
    de livrable.
    """
    interruptions = resultat.get("__interrupt__") or []
    budget = _budget(resultat)

    statut = resultat.get("statut", "erreur")
    if interruptions:
        statut = "en_attente_humain"
    elif statut == "en_cours":
        statut = "erreur"

    rapport = Rapport(
        statut=statut,
        extraction=resultat.get("extraction"),
        classification=resultat.get("classification"),
        diagnostic=resultat.get("diagnostic"),
        actions_ecartees_sans_source=resultat.get("actions_ecartees_sans_source", []),
        injections_signalees=resultat.get("injections_signalees", []),
        outils_appeles=resultat.get("outils_appeles", []),
        budget=budget.resume(),
        trace_id=id_trace,
        message=resultat.get("message", ""),
    )

    span.set_attribute(tracage.ATTR_COUT, round(budget.cout_usd, 6))
    span.set_attribute(tracage.ATTR_BUDGET_OUTILS, budget.appels_outils)
    span.set_attribute("ambicrafted.graph.path", ",".join(resultat.get("journal", [])))
    span.set_attribute(tracage.ATTR_VERDICT, statut)
    if statut in {"erreur", "budget_epuise"}:
        span.set_status(Status(StatusCode.ERROR, rapport.message or statut))

    if interruptions:
        rapport.message = json.dumps(
            interruptions[0].value, ensure_ascii=False, indent=2
        )
    tracage.vider()
    return rapport


# --- Utilitaires ----------------------------------------------------------


def _appels_outils(message: dict[str, Any]) -> list[dict[str, Any]]:
    if message.get("role") != "assistant":
        return []
    return list(message.get("tool_calls") or [])


def _lire_decision(decision: Any) -> dict[str, Any]:
    """Interprète la réponse humaine. Le silence n'est pas une approbation.

    Toute réponse qui n'est pas un accord explicite vaut refus : c'est le
    sens d'une porte. Un défaut permissif transformerait la pause en
    formalité.
    """
    if isinstance(decision, dict):
        return {
            "approuve": bool(decision.get("approuve")),
            "commentaire": str(decision.get("commentaire", "")),
        }
    texte = str(decision or "").strip()
    accords = {"oui", "o", "yes", "y", "approuve", "approuvé", "ok"}
    return {
        "approuve": texte.lower() in accords,
        "commentaire": (
            "" if texte.lower() in accords else f"Refus ou réserve de l'humain : {texte!r}"
        ),
    }
