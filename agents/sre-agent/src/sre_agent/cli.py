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
from .modeles import QualiteDiagnostic, Rapport

CODES = {"complet": 0, "budget_epuise": 2, "erreur": 3}


def rendre_budget(budget: dict) -> str:
    cout = budget.get("cout_usd")
    mesure = budget.get("cout_disponible") or (isinstance(cout, (int, float)) and cout > 0)
    cout_texte = f"{cout:.4f} USD rapportés" if mesure else "coût API inconnu"
    tokens = budget.get("tokens_total")
    tokens_texte = str(tokens) if budget.get("tokens_disponibles") else "inconnus"
    tentatives = budget.get("appels_llm_tentes", budget.get("appels_llm", 0))
    return (
        f"BUDGET : {budget['appels_outils']}/{budget['max_appels_outils']} outils, "
        f"{cout_texte} (plafond {budget['max_cout_usd']:.2f} USD), "
        f"{tentatives} tentatives LLM\n"
        f"JETONS OBSERVÉS : {tokens_texte}/{budget.get('max_tokens_total', 'inconnu')} ; "
        f"mesures complètes {budget.get('appels_mesures_tokens', 0)}/{tentatives} appels. "
        "Une mesure partielle est une borne basse."
    )


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(
        prog="sre-agent",
        description=(
            "Analyse une alerte à partir des runbooks et propose des actions. "
            "N'exécute jamais de remédiation."
        ),
    )
    analyseur.add_argument("alerte", nargs="*", help="Texte de l'alerte. À défaut, lu sur stdin.")
    analyseur.add_argument(
        "--json", action="store_true", help="Rapport complet en JSON sur stdout."
    )
    arguments = analyseur.parse_args(argv)

    texte = " ".join(arguments.alerte).strip() or sys.stdin.read(config.MAX_ALERTE + 1).strip()
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
            "PASSAGES SIGNALÉS PAR LE DÉTECTEUR : non exécutés, à vérifier",
        ]
        for texte in rapport.injections_signalees:
            lignes.append(f"  · {texte}")
        lignes.append("  Ce signalement faillible ne prouve ni une attaque ni son exécution.")

    if rapport.classification:
        c = rapport.classification
        connue = "connue" if c.connue else "INCONNUE"
        actionnable = "actionnable" if c.actionnable else "non actionnable"
        lignes += ["", f"TRI : {connue}, urgence {c.urgence}/5, {actionnable}"]
        if c.justification:
            lignes.append(f"  {c.justification}")

    if rapport.diagnostic:
        d = rapport.diagnostic
        source = d.runbook_source or "AUCUNE (non couvert par les runbooks)"
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
            lignes += ["", "ACTIONS PROPOSÉES : à exécuter par un humain"]
            lignes += [f"  {i}. {a}" for i, a in enumerate(d.actions_proposees, 1)]
        if d.qualite:
            lignes += ["", rendre_qualite(d.qualite)]

    if rapport.actions_ecartees_sans_source:
        lignes += [
            "",
            "ACTIONS ÉCARTÉES PAR LE CODE : passage absent d'une lecture vérifiée",
        ]
        lignes += [f"  · {a}" for a in rapport.actions_ecartees_sans_source]

    if rapport.outils_appeles:
        lignes += ["", "OUTILS APPELÉS : " + ", ".join(rapport.outils_appeles)]

    if b:
        lignes += ["", rendre_budget(b)]
    if rapport.trace_id and config.TRACAGE_ACTIF:
        lignes.append(f"TRACE  : {rapport.trace_id}")

    return "\n".join(lignes).strip()


def rendre_qualite(qualite: QualiteDiagnostic) -> str:
    lignes = [
        "REVUE DE COHÉRENCE IA : " + qualite.statut,
        "  " + qualite.limite,
        (
            f"  {qualite.latence_ms} ms ; tokens observés "
            f"entrée {qualite.tokens_entree}, sortie {qualite.tokens_sortie}"
        ),
    ]
    lignes += ["  · " + ecart for ecart in qualite.ecarts]
    lignes += ["  Calcul : " + calcul for calcul in qualite.calculs]
    return "\n".join(lignes)


if __name__ == "__main__":
    raise SystemExit(main())
