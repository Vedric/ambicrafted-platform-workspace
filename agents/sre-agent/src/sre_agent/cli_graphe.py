"""Command-line entry point for the graph version.

Deliberately separate from `cli.py`: `sre-agent` stays the reference
version, `sre-agent-graph` is the port. Both can be run on the same alert
and compared, which is the whole point of ADR 0004.

The life cycle differs on one point, and that point is the port itself:

    sre-agent-graph "alerte..."                 # stops at the gate
    sre-agent-graph --etat --thread-id ID       # reads the persisted state
    sre-agent-graph --reprendre oui --thread-id ID
    sre-agent-graph --purger [--avant JOURS] [--simulation]   # retention

Between the first and the third command, the process may die and the
machine may reboot. The state lives in SQLite, not in the memory of a
process.

Exit codes:
  0  analysis complete and approved
  2  budget exhausted, human escalation required
  3  run error
  4  diagnosis refused by the human
  10 waiting for human approval

The argparse strings and the rendered output below stay in French: an
on-call engineer reads them. See the language policy in CONTRIBUTING.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid

from . import config, graphe
from .cli import rendre
from .modeles import Rapport

CODES = {
    "complet": 0,
    "budget_epuise": 2,
    "erreur": 3,
    "rejete_par_humain": 4,
    "en_attente_humain": 10,
}


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(
        prog="sre-agent-graph",
        description=(
            "Même analyse que sre-agent, orchestrée par un graphe d'états. "
            "S'interrompt avant de livrer son diagnostic et attend une "
            "approbation humaine, qui peut arriver après un redémarrage."
        ),
    )
    analyseur.add_argument("alerte", nargs="*", help="Texte de l'alerte.")
    analyseur.add_argument(
        "--thread-id",
        default=None,
        help="Fil d'exécution. Obligatoire pour --reprendre et --etat.",
    )
    analyseur.add_argument(
        "--reprendre",
        metavar="DÉCISION",
        help="Reprend un fil en pause. « oui » approuve, tout le reste refuse.",
    )
    analyseur.add_argument(
        "--etat", action="store_true", help="Affiche l'état persistant, n'exécute rien."
    )
    analyseur.add_argument(
        "--checkpoints",
        default=graphe.CHEMIN_CHECKPOINTS,
        help="Fichier SQLite des checkpoints.",
    )
    analyseur.add_argument(
        "--purger",
        action="store_true",
        help=(
            "Supprime les fils sans activité depuis plus de --avant jours, "
            "puis compacte le fichier. N'exécute rien d'autre."
        ),
    )
    analyseur.add_argument(
        "--avant",
        metavar="JOURS",
        type=int,
        default=graphe.RETENTION_JOURS,
        help=(
            "Avec --purger : ancienneté au-delà de laquelle un fil est purgé "
            f"(défaut : {graphe.RETENTION_JOURS}, variable SRE_RETENTION_JOURS)."
        ),
    )
    analyseur.add_argument(
        "--simulation",
        action="store_true",
        help="Avec --purger : liste ce qui serait supprimé, ne supprime rien.",
    )
    analyseur.add_argument("--json", action="store_true", help="Sortie JSON.")
    arguments = analyseur.parse_args(argv)

    if arguments.simulation and not arguments.purger:
        analyseur.error("--simulation n'a de sens qu'avec --purger.")
    if arguments.purger:
        if arguments.avant < 0:
            analyseur.error("--avant doit être positif ou nul.")
        bilan = graphe.purger(
            arguments.avant, arguments.checkpoints, simulation=arguments.simulation
        )
        if arguments.json:
            print(json.dumps(bilan, ensure_ascii=False, indent=2))
        else:
            print(rendre_purge(bilan))
        return 0

    if arguments.etat:
        if not arguments.thread_id:
            analyseur.error("--etat exige --thread-id.")
        instantane = graphe.etat(arguments.thread_id, arguments.checkpoints)
        print(
            json.dumps(
                {k: v for k, v in instantane.items() if k != "valeurs"},
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        return 0 if instantane["existe"] else 3

    if arguments.reprendre is not None:
        if not arguments.thread_id:
            analyseur.error("--reprendre exige --thread-id.")
        rapport = graphe.reprendre(
            arguments.reprendre, arguments.thread_id, arguments.checkpoints
        )
        fil = arguments.thread_id
    else:
        texte = " ".join(arguments.alerte).strip() or sys.stdin.read().strip()
        if not texte:
            analyseur.error("Aucune alerte fournie, ni en argument ni sur stdin.")
        fil = arguments.thread_id or f"sre-{uuid.uuid4().hex[:12]}"
        rapport = graphe.demarrer(texte, fil, arguments.checkpoints)

    if arguments.json:
        charge = rapport.model_dump(mode="json")
        charge["thread_id"] = fil
        print(json.dumps(charge, ensure_ascii=False, indent=2))
    else:
        print(rendre_graphe(rapport, fil, arguments.checkpoints))

    return CODES.get(rapport.statut, 3)


def rendre_graphe(rapport: Rapport, thread_id: str, chemin_db: str) -> str:
    """Human rendering. Reuses `cli.rendre`: same deliverable, same shape.

    Only the pause needs handling specific to the graph, because it does
    not exist in the hand-written version.
    """
    if rapport.statut == "en_attente_humain":
        demande = json.loads(rapport.message) if rapport.message else {}
        lignes = [
            "EN PAUSE : approbation humaine requise avant livraison",
            "",
            f"  {demande.get('demande', '')}",
            "",
            f"CAUSE PROBABLE (confiance : {demande.get('confiance', '?')})",
            f"  {demande.get('cause_probable', '')}",
            "",
            f"SOURCE : {demande.get('runbook_source') or 'AUCUNE (non couvert par les runbooks)'}",
        ]
        if actions := demande.get("actions_proposees"):
            lignes += ["", "ACTIONS SOUMISES À APPROBATION"]
            lignes += [f"  {i}. {a}" for i, a in enumerate(actions, 1)]
        if ecartees := demande.get("actions_ecartees_sans_source"):
            lignes += ["", "ACTIONS DÉJÀ ÉCARTÉES PAR LE CODE : aucune source"]
            lignes += [f"  · {a}" for a in ecartees]
        if outils := demande.get("outils_appeles"):
            lignes += ["", "OUTILS APPELÉS : " + ", ".join(outils)]
        b = demande.get("budget") or {}
        if b:
            lignes += [
                "",
                (
                    f"BUDGET : {b['appels_outils']}/{b['max_appels_outils']} outils, "
                    f"{b['cout_usd']:.4f}/{b['max_cout_usd']:.2f} USD, "
                    f"{b['appels_llm']} appels LLM"
                ),
            ]
        if rapport.trace_id and config.TRACAGE_ACTIF:
            lignes.append(f"TRACE  : {rapport.trace_id}")
        lignes += [
            "",
            "L'état est persisté. Ce processus peut être arrêté sans perte.",
            "Pour livrer :",
            f"  sre-agent-graph --thread-id {thread_id} --reprendre oui",
            "Pour refuser :",
            f"  sre-agent-graph --thread-id {thread_id} --reprendre \"non, ...\"",
            f"CHECKPOINTS : {chemin_db}",
        ]
        return "\n".join(lignes).strip()

    corps = rendre(rapport)
    entete = []
    if rapport.statut == "rejete_par_humain":
        entete = ["REFUSÉ PAR L'HUMAIN : rien n'est livré", "", f"  {rapport.message}", ""]
    elif rapport.statut == "complet":
        entete = ["APPROUVÉ PAR L'HUMAIN", ""]
    return "\n".join([*entete, corps, "", f"THREAD : {thread_id}"]).strip()


def rendre_purge(bilan: dict) -> str:
    """Human rendering of the purge summary."""
    titre = "À PURGER (simulation, rien n'est supprimé)" if bilan["simulation"] else "PURGÉ"
    lignes = [
        f"{titre} : {len(bilan['purges'])} fil(s) sans activité depuis le "
        f"{bilan['seuil'][:10]} ; {bilan['conserves']} conservé(s)"
    ]
    for p in bilan["purges"]:
        etat = "en pause sur la porte humaine" if p["en_pause"] else "terminé"
        quand = (p["derniere_activite"] or "date inconnue")[:16]
        lignes.append(f"  · {p['thread_id']}  dernière activité {quand}  ({etat})")
    lignes.append(
        f"FICHIER : {bilan['fichier']} ({bilan['octets_avant']} → {bilan['octets_apres']} octets)"
    )
    return "\n".join(lignes)


if __name__ == "__main__":
    raise SystemExit(main())
