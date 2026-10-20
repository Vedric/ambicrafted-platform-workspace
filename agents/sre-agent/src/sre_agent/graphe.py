"""The same analysis, orchestrated by a state graph.

This module is the counterpart of `agent.py`, not its replacement. Both
produce an identical `Rapport` on top of exactly the same guardrails:
`llm.appeler_llm`, `outils.executer_outil`, `prompts.bloc`,
`budget.Budget`, `modeles.appliquer_garde_source`. Shared guardrails apply
to both implementations; ADR 0009 records the strengthened delivery contract.

What the graph adds, and the hand-written loop cannot do:

  extraction ─> classification ─> raisonnement <──┐
                                       │          │
                                       ├──> recherche_runbooks
                                       │
                                       ├──> diagnostic ──> porte_humaine ──> END
                                       │         └── retry ────┘
                                       └──> abandon ──> END

`porte_humaine` calls `interrupt()`: the graph writes its complete state
to SQLite and hands control back BEFORE delivering the diagnosis. The
process may die. A later resume on the same `thread_id`, with
`Command(resume=...)`, picks up exactly there, context intact.

Two behavioural differences from `agent.py` are accepted, both of them
stricter, and documented in ADR 0004:

1. The tool budget is enforced by a conditional edge, so BEFORE entering
   the node. A burst of three tools requested when only two remain is
   refused wholesale; the hand-written loop would have run two and then
   raised. Both stop without a half-result.
2. The finalisation retry is an edge, not an `except`: it is visible in
   the trace and in the state journal.
"""

from __future__ import annotations

import contextlib
import fcntl
import functools
import json
import operator
import os
import sqlite3
import stat
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, TypedDict, cast

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
    message_erreur,
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

# The token ceilings and the two decoding functions come from `agent.py`.
# Copying them here would give two settings that drift apart on the first
# edit, and the comparison would then measure that drift instead of
# measuring the orchestration.

CHEMIN_CHECKPOINTS = os.environ.get(
    "SRE_CHECKPOINT_DB",
    os.path.expanduser("~/.local/state/sre-agent/graphe.sqlite"),
)

# Thread retention, in days. 14: how long Tempo keeps traces
# (block_retention, 336 h), so a thread and its trace expire together, and
# one on-call rotation. See ADR 0004, Consequences.
RETENTION_JOURS = int(config._nombre("SRE_RETENTION_JOURS", 14))
VERSION_CONTRAT = 2


# --- State ----------------------------------------------------------------


class EtatSRE(TypedDict, total=False):
    """The shared state: typed, and above all serialisable.

    Everything that has to survive the death of the process is here. What
    is not (the MCP session, the HTTP client) is a process resource,
    re-established on resume.

    The fields annotated with `operator.add` are accumulators: two nodes
    writing within the same super-step concatenate their contributions
    instead of the last one overwriting the first. That is the reducer's
    technical reason to exist, and it holds for a sequential graph like
    this one too: the cycle
    raisonnement -> recherche_runbooks -> raisonnement writes to
    `messages` on every turn, and overwrite semantics would lose the tool
    history on each pass.
    """

    extraction: Extraction | None
    classification: ClassificationAlerte | None
    diagnostic: Diagnostic | None
    sources_lues: dict[str, str]

    # --- Accumulators ----------------------------------------------------
    messages: Annotated[list[dict[str, Any]], operator.add]
    outils_appeles: Annotated[list[str], operator.add]
    injections_signalees: Annotated[list[str], operator.add]
    actions_ecartees_sans_source: Annotated[list[str], operator.add]
    journal: Annotated[list[str], operator.add]
    # The budget is NOT stored as a total, but as the sequence of its
    # charges. A total would be overwritten by the last branch to write;
    # a list of deltas adds up. The counter is then replayed by
    # `_budget()`, which makes it as accurate after a resume as it was
    # before the interruption.
    depenses: Annotated[list[dict[str, float]], operator.add]

    # --- Control ---------------------------------------------------------
    version_contrat: int
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
    "appels_llm_tentes",
    "cout_usd",
    "tokens_entree",
    "tokens_sortie",
    "appels_mesures_tokens",
    "appels_mesures_entree",
    "appels_mesures_sortie",
    "appels_mesures_cout",
)


def _budget(etat: EtatSRE) -> Budget:
    """Replay the recorded charges to rebuild the budget.

    The counters are assigned directly rather than replayed through
    `consommer_llm`, which would raise in the middle of the replay. This
    is not a way around the guardrail: the ceilings are still those of
    `config`, and it is still `Budget` that enforces them on the next real
    call. The semantics of `agent.py` are preserved: an overrun is
    observed after the fact and stops the following step.
    """
    budget = Budget(
        max_appels_outils=config.MAX_APPELS_OUTILS,
        max_cout_usd=config.MAX_COUT_USD,
    )
    budget.sources_lues = dict(etat.get("sources_lues") or {})
    if _echeance is not None:
        budget.echeance = _echeance
    for depense in etat.get("depenses") or []:
        for champ in _CHAMPS_BUDGET:
            valeur = depense.get(champ, 0)
            if champ == "appels_llm_tentes" and champ not in depense:
                valeur = depense.get("appels_llm", 0)
            setattr(budget, champ, getattr(budget, champ) + valeur)
    return budget


def _instantane(budget: Budget) -> dict[str, float]:
    return {champ: getattr(budget, champ) for champ in _CHAMPS_BUDGET}


def _delta(avant: dict[str, float], budget: Budget) -> dict[str, float]:
    return {champ: getattr(budget, champ) - avant[champ] for champ in _CHAMPS_BUDGET}


# --- Tracing context and tool session -------------------------------------
#
# Two resources cannot live in the serialised state: the parent span and
# the MCP subprocess. They are therefore held by the process, installed by
# `_execution()` and read by the nodes. One graph run per process, which is
# how the CLI is meant to be used.

_contexte_parent: Any = None
_pile_ressources: contextlib.ExitStack | None = None
_client_runbooks: ClientRunbooks | None = None
_alerte_courante: str | None = None
_echeance: float | None = None
_verrou_execution = threading.Lock()


def _client() -> ClientRunbooks:
    """Open the MCP session on first request, never earlier.

    A resume after approval calls no more tools: paying for the
    subprocess start-up would be paying for nothing.
    """
    global _client_runbooks
    if _client_runbooks is None:
        if _pile_ressources is None:
            raise ErreurOutil("Nœud d'outils exécuté hors d'une exécution de graphe.")
        _client_runbooks = _pile_ressources.enter_context(ClientRunbooks())
    return _client_runbooks


def noeud(nom: str):
    """Wrap a node: one child span, and errors recorded into the state.

    This is where point 3 of the port plays out. A node never decides what
    comes next: it does its work, or it records why it could not, and
    hands back. Routing is the business of the edges.

    The spend is computed as a before/after difference, including when the
    node fails: a call that was paid for and then rejected is still paid
    for, and the report has to say so.
    """

    def decorateur(fonction):
        @functools.wraps(fonction)
        def enveloppe(etat: EtatSRE) -> dict[str, Any]:
            budget = _budget(etat)
            avant = _instantane(budget)
            with tracage.tracer().start_as_current_span(
                f"node.{nom}",
                context=_contexte_parent,
                record_exception=False,
                set_status_on_exception=False,
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
                    config.ConfigurationInvalide,
                ) as e:
                    maj = {"statut": "erreur", "message": message_erreur(e), "diagnostic": None}
                    span.set_attribute(tracage.ATTR_VERDICT, "error")
                    span.set_status(Status(StatusCode.ERROR, maj["message"]))

                depense = _delta(avant, budget)
                if any(depense.values()):
                    maj["depenses"] = [*maj.get("depenses", []), depense]
                maj["journal"] = [*maj.get("journal", []), nom]
                if budget.outils_appeles:
                    maj["outils_appeles"] = list(budget.outils_appeles)
                maj["sources_lues"] = budget.sources_lues
                if budget.appels_mesures_cout or budget.cout_usd:
                    span.set_attribute("ambicrafted.budget.spent_usd", round(budget.cout_usd, 6))
                span.set_attribute(tracage.ATTR_BUDGET_OUTILS, budget.appels_outils)
                return maj

        return enveloppe

    return decorateur


# --- Nodes ----------------------------------------------------------------


@noeud("extraction")
def extraction(etat: EtatSRE, budget: Budget) -> dict[str, Any]:
    """Raw alert -> anonymised form. Local, classified CONFIDENTIEL.

    The raw alert is held only in invocation memory. Derived fields remain
    confidential throughout the graph and can retain customer information.
    The classification passed to `appeler_llm` refuses a frontier alias.
    """
    if _alerte_courante is None:
        raise ErreurPasserelle(
            "Alerte absente de la mémoire du processus ; démarrer un nouveau fil."
        )
    reponse = appeler_llm(
        alias=config.ALIAS_EXTRACTION,
        messages=prompts.messages_extraction(_alerte_courante),
        classification=Classification.CONFIDENTIEL,
        budget=budget,
        tache="extraction",
        max_tokens=MAX_TOKENS_LOCAL,
        schema_json=Extraction.schema_sortie(),
    )
    extrait = Extraction.model_validate(extraire_json(reponse.contenu))
    return {
        "extraction": extrait,
        "injections_signalees": list(extrait.instructions_detectees),
    }


@noeud("classification")
def classification(etat: EtatSRE, budget: Budget) -> dict[str, Any]:
    """Triage over confidential extracted data, using the local alias.

    The node seeds `messages` with the system prompt and the payload:
    later turns only append to it, never replace it, thanks to the
    reducer.
    """
    extrait = etat["extraction"]
    if extrait is None:
        raise ErreurPasserelle("Extraction absente.")
    reponse = appeler_llm(
        alias=config.ALIAS_CLASSIFICATION,
        messages=prompts.messages_classification(extrait),
        classification=Classification.CONFIDENTIEL,
        budget=budget,
        tache="classification",
        max_tokens=MAX_TOKENS_TRI,
        schema_json=ClassificationAlerte.schema_sortie(),
    )
    tri = ClassificationAlerte.depuis_modele(extraire_json(reponse.contenu))
    return {
        "classification": tri,
        "messages": prompts.messages_raisonnement(extrait, tri),
    }


@noeud("raisonnement")
def raisonnement(etat: EtatSRE, budget: Budget) -> dict[str, Any]:
    """One turn of the tool-using model. Just one: the cycle is in the graph.

    The tools stay declared even once the budget is spent, exactly as in
    `agent.py`: removing them would make the model answer without having
    consulted the runbooks, and that degraded answer would be returned as
    a diagnosis.
    """
    reponse = appeler_llm(
        alias=config.ALIAS_RAISONNEMENT,
        messages=prompts.avec_observations_originales(etat["messages"], _alerte_courante),
        classification=Classification.CONFIDENTIEL,
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
    """Run the MCP tools requested on the previous turn.

    `executer_outil` charges the budget before calling the server and
    raises if the ceiling is reached. The incoming edge has normally ruled
    that case out already; the guardrail stays in place and is what
    counts.
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
    """Validate the final JSON and apply the source guard.

    When prose comes back, the node does not retry by itself: it records
    the retry request in the state, and the edge decides to go through
    `raisonnement` again. The difference is not cosmetic: the retry
    becomes an observable edge traversal instead of an `except` invisible
    from the outside.
    """
    contenu = etat["messages"][-1].get("content") or ""
    try:
        brut = Diagnostic.model_validate(extraire_json(contenu))
    except ErreurPasserelle, ValidationError:
        if etat.get("relance_tentee"):
            raise ErreurPasserelle(
                "Le modèle n'a pas produit de diagnostic exploitable après relance."
            ) from None
        return {
            "relance_tentee": True,
            "diagnostic": None,
            "messages": [{"role": "user", "content": prompts.RELANCE_FINALISATION}],
        }

    retenu, ecartees = appliquer_garde_source(brut, budget.sources_lues)
    return {"diagnostic": retenu, "actions_ecartees_sans_source": ecartees}


@noeud("porte_humaine")
def porte_humaine(etat: EtatSRE, budget: Budget) -> dict[str, Any]:
    """The node that justifies the port: a durable pause before delivery.

    `interrupt()` raises a control exception that LangGraph catches after
    writing the state to the checkpointer. So what is delivered was never
    delivered without a human having seen it, and that property holds even
    if the machine stops during the pause.

    The span is closed without an error: an expected pause is not an
    incident, and marking it red would make the dashboard unreadable on
    the day the gate really matters.
    """
    d = etat["diagnostic"]
    if d is None:
        raise ErreurPasserelle("Diagnostic absent de la demande d'approbation.")
    decision = interrupt(
        {
            "demande": "Approuver la livraison de ce diagnostic ?",
            "cause_probable": d.cause_probable,
            "confiance": d.confiance.value,
            "runbook_source": d.runbook_source,
            "actions_proposees": d.actions_proposees,
            "elements_manquants": d.elements_manquants,
            "injections_signalees": etat.get("injections_signalees", []),
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
        "diagnostic": d if approbation["approuve"] else None,
    }


@noeud("abandon")
def abandon(etat: EtatSRE, budget: Budget) -> dict[str, Any]:
    """Clean exit. No partial diagnosis is presented as complete.

    The node replays the routing conditions to say which of the three
    ceilings actually bit. That is not cosmetic: "tool ceiling" and "turn
    ceiling" call for opposite fixes, and at 3 a.m. nobody is going to
    re-read the graph to work it out.
    """
    if etat.get("statut") == "erreur":
        return {"diagnostic": None}
    return {
        "statut": "budget_epuise",
        "message": _motif_abandon(etat, budget),
        "diagnostic": None,
    }


def _motif_abandon(etat: EtatSRE, budget: Budget) -> str:
    """Attribute the stop to the ceiling that actually caused it."""
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


# --- Conditional edges ----------------------------------------------------
#
# All the exit logic lives here, in the open, in pure functions that read
# the state and return a node name. That is point 3 of the port: a budget
# overrun is a fork in the graph, not an `if` in the middle of a loop.


def _sortie_forcee(etat: EtatSRE) -> str | None:
    if etat.get("motif_abandon") or etat.get("statut") == "erreur":
        return "abandon"
    return None


def _budget_epuise(etat: EtatSRE) -> bool:
    return _budget(etat).cout_usd >= config.MAX_COUT_USD


def apres_extraction(etat: EtatSRE) -> str:
    return _sortie_forcee(etat) or ("abandon" if _budget_epuise(etat) else "classification")


def apres_classification(etat: EtatSRE) -> str:
    return _sortie_forcee(etat) or ("abandon" if _budget_epuise(etat) else "raisonnement")


def apres_raisonnement(etat: EtatSRE) -> str:
    """Tools, diagnosis or abort. Decided on the state, not inside the node."""
    if forcee := _sortie_forcee(etat):
        return forcee
    demandes = _appels_outils(etat["messages"][-1])
    if not demandes:
        return "diagnostic"
    if etat.get("tours", 0) >= config.MAX_TOURS:
        return "abandon"
    # The budget is enforced before entering the node: a burst wider than
    # what remains is refused wholesale, not half executed.
    if len(demandes) > _budget(etat).outils_restants():
        return "abandon"
    return "recherche_runbooks"


def apres_outils(etat: EtatSRE) -> str:
    return _sortie_forcee(etat) or (
        "abandon"
        if _budget_epuise(etat) or etat.get("tours", 0) >= config.MAX_TOURS
        else "raisonnement"
    )


def apres_diagnostic(etat: EtatSRE) -> str:
    if forcee := _sortie_forcee(etat):
        return forcee
    if etat.get("diagnostic") is None:
        # Retry requested: the model returned prose. Once only, and
        # `relance_tentee` is what attests to it on the node side.
        return (
            "abandon"
            if _budget_epuise(etat) or etat.get("tours", 0) >= config.MAX_TOURS
            else "raisonnement"
        )
    return "porte_humaine"


# --- Assembly -------------------------------------------------------------


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
    graphe.add_conditional_edges("extraction", apres_extraction, ["classification", "abandon"])
    graphe.add_conditional_edges(
        "classification", apres_classification, ["raisonnement", "abandon"]
    )
    graphe.add_conditional_edges(
        "raisonnement",
        apres_raisonnement,
        ["recherche_runbooks", "diagnostic", "abandon"],
    )
    graphe.add_conditional_edges("recherche_runbooks", apres_outils, ["raisonnement", "abandon"])
    graphe.add_conditional_edges(
        "diagnostic", apres_diagnostic, ["porte_humaine", "raisonnement", "abandon"]
    )
    graphe.add_edge("porte_humaine", END)
    graphe.add_edge("abandon", END)
    return graphe


# The checkpointer is a trust boundary the hand-written loop did not have:
# a persistent file the graph reads back and deserialises. By default
# LangGraph accepts any Python type there, which its own documentation
# flags as a code-execution vector for anyone able to write to that file.
# So it gets the same shape as `OUTILS_AUTORISES`: a closed allowlist,
# owned by this repository.
TYPES_PERSISTABLES = (Extraction, ClassificationAlerte, Diagnostic, Confiance)


def _serialiseur() -> JsonPlusSerializer:
    return JsonPlusSerializer(
        pickle_fallback=False,
        allowed_msgpack_modules=TYPES_PERSISTABLES,
    )


def compiler(chemin_db: str = CHEMIN_CHECKPOINTS):
    """Compile the graph onto a SQLite checkpointer.

    SQLite and not Postgres: the agent's persistence must not depend on
    the gateway's database. An agent going down because the gateway's
    accounting is under maintenance would be gratuitous coupling between
    two unrelated concerns. The upgrade path is documented in ADR 0004.

    The file is created 0600: it holds the alert's extraction, therefore
    data derived from customer data, and it outlives the process. A
    persistent state readable by the whole system would cancel part of the
    benefit of the compartmentalisation.
    """
    dossier = os.path.dirname(os.path.abspath(chemin_db)) or "."
    os.makedirs(dossier, mode=0o700, exist_ok=True)
    info = os.stat(dossier)
    if info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise config.ConfigurationInvalide(
            "Le dossier de checkpoints doit appartenir à l'utilisateur "
            "et ne pas être modifiable par un tiers."
        )
    fd = os.open(chemin_db, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise config.ConfigurationInvalide("Le checkpoint doit être un fichier régulier.")
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)
    connexion = sqlite3.connect(chemin_db, check_same_thread=False)
    connexion.execute("PRAGMA secure_delete=ON")
    return construire().compile(checkpointer=SqliteSaver(connexion, serde=_serialiseur()))


@contextlib.contextmanager
def _application(chemin_db: str):
    application = compiler(chemin_db)
    fd = None
    try:
        fd = os.open(chemin_db + ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ErreurPasserelle(
                "La base de checkpoints est utilisée par une autre exécution."
            ) from None
        yield application
    finally:
        application.checkpointer.conn.close()
        if fd is not None:
            os.close(fd)


# --- Execution ------------------------------------------------------------


@contextlib.contextmanager
def _execution(trace_origine: dict[str, str] | None, alerte: str | None = None):
    """Install the parent span and tool session for the length of an invoke.

    A resume after an interruption necessarily opens a new trace: the old
    one died with the process. Rather than pretend otherwise, the new one
    is explicitly tied to the old through an OTel Link, and Grafana shows
    both halves of a single story.
    """
    global _contexte_parent, _pile_ressources, _client_runbooks
    global _alerte_courante, _echeance

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

    if not _verrou_execution.acquire(blocking=False):
        raise ErreurOutil("Une analyse de graphe est déjà active dans ce processus.")
    with contextlib.ExitStack() as pile:
        pile.callback(_verrou_execution.release)
        _pile_ressources = pile
        _client_runbooks = None
        _alerte_courante = alerte
        _echeance = time.monotonic() + config.MAX_DUREE_S
        span = pile.enter_context(
            tracage.tracer().start_as_current_span("task.incident_analysis", links=liens)
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
            yield (
                span,
                format(contexte.trace_id, "032x"),
                {
                    "trace_id": format(contexte.trace_id, "032x"),
                    "span_id": format(contexte.span_id, "016x"),
                },
            )
        finally:
            _contexte_parent = None
            _pile_ressources = None
            _client_runbooks = None
            _alerte_courante = None
            _echeance = None


def demarrer(alerte: str, thread_id: str, chemin_db: str = CHEMIN_CHECKPOINTS) -> Rapport:
    """Start an analysis. Stops at the human gate."""
    try:
        config.valider(alerte)
        configuration = _configuration(thread_id)
        with _application(chemin_db) as application:
            if application.get_state(configuration).created_at:
                return Rapport(
                    statut="erreur",
                    message="Ce thread existe déjà. Reprendre le fil "
                    "en pause ou choisir un nouvel identifiant pour un nouvel incident.",
                )
            with _execution(None, alerte) as (span, id_trace, origine):
                etat_initial: EtatSRE = {
                    "version_contrat": VERSION_CONTRAT,
                    "statut": "en_cours",
                    "trace_id": id_trace,
                    "trace_origine": origine,
                }
                resultat = application.invoke(etat_initial, configuration)
                return _finaliser(span, resultat, id_trace)
    except (config.ConfigurationInvalide, ErreurPasserelle, ErreurOutil) as e:
        return Rapport(statut="erreur", message=message_erreur(e))
    except (OSError, sqlite3.Error) as e:
        return Rapport(statut="erreur", message=f"Persistance indisponible : {type(e).__name__}.")


def _configuration(thread_id: str) -> dict[str, Any]:
    if not isinstance(thread_id, str) or not thread_id.strip() or len(thread_id) > 128:
        raise config.ConfigurationInvalide("Identifiant de thread vide ou trop long.")
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": config.MAX_TOURS * 3 + 12}


def reprendre(decision: str, thread_id: str, chemin_db: str = CHEMIN_CHECKPOINTS) -> Rapport:
    """Resume a paused analysis, on the same thread_id.

    No alert argument: everything needed is already in the checkpoint.
    That is precisely the demonstration.
    """
    from langgraph.types import Command

    try:
        config.valider()
        configuration = _configuration(thread_id)
        with _application(chemin_db) as application:
            instantane = application.get_state(configuration)
            if (
                instantane.created_at
                and instantane.values.get("version_contrat") != VERSION_CONTRAT
            ):
                return Rapport(
                    statut="erreur",
                    message="Checkpoint incompatible avec les garanties actuelles. "
                    "Relancer l'analyse avec un nouvel identifiant de fil.",
                )
            if not instantane.created_at or not instantane.interrupts:
                return Rapport(
                    statut="erreur", message="Aucun diagnostic en attente sur ce thread."
                )
            origine = instantane.values.get("trace_origine")
            with _execution(origine) as (span, id_trace, _):
                resultat = application.invoke(Command(resume=decision), configuration)
                return _finaliser(span, resultat, origine.get("trace_id") if origine else id_trace)
    except (config.ConfigurationInvalide, ErreurPasserelle, ErreurOutil) as e:
        return Rapport(statut="erreur", message=message_erreur(e))
    except (OSError, sqlite3.Error) as e:
        return Rapport(statut="erreur", message=f"Persistance indisponible : {type(e).__name__}.")


def etat(thread_id: str, chemin_db: str = CHEMIN_CHECKPOINTS) -> dict[str, Any]:
    """Read the persisted state without running anything."""
    with _application(chemin_db) as application:
        instantane = application.get_state(_configuration(thread_id))
    interruptions = [i.value for i in (getattr(instantane, "interrupts", None) or ())]
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
    """Delete threads with no activity for more than `avant_jours` days.

    A thread's age is that of its last checkpoint, as the checkpointer
    timestamped it (`created_at`, the same source as `etat`). A thread
    paused at the human gate ages like the others and is purged like the
    others: an approval that has not come in two weeks will not come, the
    alert was handled another way. The summary flags it (`en_pause`) so
    the operator can see it.

    Deleting the rows is not enough: SQLite keeps the freed pages inside
    the file, and the WAL journal holds a copy. Hence VACUUM followed by
    truncating the WAL, without which alert-derived data survives its own
    "purge".
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
        return bilan  # nothing to purge, and above all do not create the file

    bilan["octets_avant"] = _empreinte(chemin_db)
    with _application(chemin_db) as application:
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
    bilan["octets_apres"] = _empreinte(chemin_db)
    return bilan


def _empreinte(chemin_db: str) -> int:
    """Bytes actually occupied: the file and its WAL journal.

    In WAL mode the main file can be a single page while the whole state
    lives in `-wal`; measuring one without the other lies.
    """
    return sum(os.path.getsize(c) for c in (chemin_db, chemin_db + "-wal") if os.path.exists(c))


def _finaliser(span: Any, resultat: dict[str, Any], id_trace: str | None) -> Rapport:
    """Assemble the Rapport, the same object as the one from `agent.py`.

    The output contract does not change from one implementation to the
    other: that is what allows the CLI rendering to be reused, and above
    all what forbids dressing up an orchestration difference as a
    difference in the deliverable.
    """
    interruptions = resultat.get("__interrupt__") or []
    budget = _budget(cast(EtatSRE, resultat))

    statut = resultat.get("statut", "erreur")
    if interruptions:
        statut = "en_attente_humain"
    elif statut == "en_cours":
        statut = "erreur"

    rapport = Rapport(
        statut=statut,
        extraction=resultat.get("extraction"),
        classification=resultat.get("classification"),
        diagnostic=resultat.get("diagnostic") if statut == "complet" else None,
        actions_ecartees_sans_source=(
            resultat.get("actions_ecartees_sans_source", []) if statut == "complet" else []
        ),
        injections_signalees=resultat.get("injections_signalees", []),
        outils_appeles=resultat.get("outils_appeles", []),
        budget=budget.resume(),
        trace_id=id_trace,
        message=resultat.get("message", ""),
    )

    if budget.appels_mesures_cout or budget.cout_usd:
        span.set_attribute(tracage.ATTR_COUT_TOTAL, round(budget.cout_usd, 6))
    span.set_attribute(tracage.ATTR_BUDGET_OUTILS, budget.appels_outils)
    span.set_attribute("ambicrafted.graph.path", ",".join(resultat.get("journal", [])))
    span.set_attribute(tracage.ATTR_VERDICT, statut)
    if statut in {"erreur", "budget_epuise"}:
        span.set_status(Status(StatusCode.ERROR, rapport.message or statut))

    if interruptions:
        rapport.message = json.dumps(interruptions[0].value, ensure_ascii=False, indent=2)
    tracage.vider()
    return rapport


# --- Helpers --------------------------------------------------------------


def _appels_outils(message: dict[str, Any]) -> list[dict[str, Any]]:
    if message.get("role") != "assistant":
        return []
    return list(message.get("tool_calls") or [])


def _lire_decision(decision: Any) -> dict[str, Any]:
    """Interpret the human answer. Silence is not approval.

    Any answer that is not an explicit agreement counts as a refusal:
    that is what a gate means. A permissive default would turn the pause
    into a formality.
    """
    if isinstance(decision, dict):
        return {
            "approuve": decision.get("approuve") is True,
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
