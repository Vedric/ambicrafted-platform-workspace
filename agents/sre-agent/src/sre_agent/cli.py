"""Command-line entry point.

The agent reads an alert from an argument or from stdin, and returns
either a report an on-call human can read, or JSON for a machine caller.

The exit code carries meaning:
  0  complete analysis
  2  budget exhausted, human escalation required
  3  run error

The argparse strings and the rendered report below stay in French: an
on-call engineer reads them. See the language policy in CONTRIBUTING.md.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import config
from .agent import analyser
from .modeles import Rapport

CODES = {"complet": 0, "budget_epuise": 2, "erreur": 3}


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(
        prog="sre-agent",
        description=(
            "Analyse une alerte à partir des runbooks et propose des actions. "
            "N'exécute jamais de remédiation."
        ),
    )
    analyseur.add_argument(
        "alerte", nargs="*", help="Texte de l'alerte. À défaut, lu sur stdin."
    )
    analyseur.add_argument(
        "--json", action="store_true", help="Rapport complet en JSON sur stdout."
    )
    arguments = analyseur.parse_args(argv)

    texte = " ".join(arguments.alerte).strip() or sys.stdin.read().strip()
    if not texte:
        analyseur.error("Aucune alerte fournie, ni en argument ni sur stdin.")

    rapport = analyser(texte)

    if arguments.json:
        print(json.dumps(rapport.model_dump(mode="json"), ensure_ascii=False, indent=2))
    else:
        print(rendre(rapport))

    return CODES.get(rapport.statut, 3)


def rendre(rapport: Rapport) -> str:
    """Human-readable report. What was refused is as visible as what succeeded."""
    lignes: list[str] = []
    b = rapport.budget

    if rapport.statut == "budget_epuise":
        lignes += [
            "ARRÊT SOUS BUDGET",
            "",
            f"  {rapport.message}",
            "",
            "  Aucun diagnostic n'est produit. Un diagnostic partiel présenté",
            "  comme complet serait plus dangereux que pas de diagnostic.",
        ]
    elif rapport.statut == "erreur":
        lignes += ["ERREUR", "", f"  {rapport.message}"]

    if rapport.injections_signalees:
        lignes += [
            "",
            "TENTATIVE D'INJECTION DANS L'ALERTE — rapportée, non suivie",
        ]
        for texte in rapport.injections_signalees:
            lignes.append(f"  · {texte}")
        lignes.append(
            "  L'alerte est peut-être forgée : confirmer son contenu à la source."
        )

    if rapport.classification:
        c = rapport.classification
        connue = "connue" if c.connue else "INCONNUE"
        actionnable = "actionnable" if c.actionnable else "non actionnable"
        lignes += ["", f"TRI : {connue}, urgence {c.urgence}/5, {actionnable}"]
        if c.justification:
            lignes.append(f"  {c.justification}")

    if rapport.diagnostic:
        d = rapport.diagnostic
        source = d.runbook_source or "AUCUNE — non couvert par les runbooks"
        lignes += [
            "",
            f"DIAGNOSTIC (confiance : {d.confiance.value})",
            f"  {d.cause_probable}",
            "",
            f"SOURCE : {source}",
        ]
        if d.elements_manquants:
            lignes += ["", "ÉLÉMENTS MANQUANTS"]
            lignes += [f"  · {e}" for e in d.elements_manquants]
        if d.actions_proposees:
            lignes += ["", "ACTIONS PROPOSÉES — à exécuter par un humain"]
            lignes += [f"  {i}. {a}" for i, a in enumerate(d.actions_proposees, 1)]

    if rapport.actions_ecartees_sans_source:
        lignes += [
            "",
            "ACTIONS ÉCARTÉES PAR LE CODE — aucune source de runbook déclarée",
        ]
        lignes += [f"  · {a}" for a in rapport.actions_ecartees_sans_source]

    if rapport.outils_appeles:
        lignes += ["", "OUTILS APPELÉS : " + ", ".join(rapport.outils_appeles)]

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

    return "\n".join(lignes).strip()


if __name__ == "__main__":
    raise SystemExit(main())
