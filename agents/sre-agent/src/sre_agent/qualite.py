"""Bounded consistency review and deterministic, source-bound arithmetic.

The model selects claims and evidence; it cannot certify its own correctness.
Code validates literal provenance and declared arithmetic, not arbitrary prose.
The review may veto a proposal, never repair it or manufacture an action.
Original evidence and review quotations are invocation-local, not checkpointed.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import config, prompts
from .budget import Budget
from .config import Classification
from .llm import ErreurPasserelle, ReponseLLM, extraire_json
from .modeles import Confiance, Diagnostic, Extraction, QualiteDiagnostic

Texte = Annotated[str, Field(min_length=1, max_length=1600)]
Champ = Literal[
    "extraction.signature_technique",
    "extraction.symptomes",
    "extraction.composants",
    "diagnostic.cause_probable",
    "diagnostic.elements_manquants",
    "diagnostic.actions_proposees",
]


class ContratRevue(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Ecart(ContratRevue):
    reference: Annotated[str, Field(pattern=r"^p[0-9]{1,3}$")]
    nature: Literal[
        "aucun", "quantite", "chronologie", "execution", "attribution", "portee", "preuve_absente"
    ] = Field(
        description="Nature d'une erreur matérielle établie, pas le thème du texte. "
        "Une question ou une action future n'affirme pas son exécution. "
        "aucun si aucune erreur de la proposition n'est établie."
    )


class Operande(ContratRevue):
    contexte: Texte
    valeur: Annotated[str, Field(min_length=1, max_length=100)]


class Calcul(ContratRevue):
    champ: Champ
    citation: Texte
    operation: Literal["comparaison", "pourcentage", "ecart_relatif", "difference"]
    gauche: Operande
    droite: Operande
    # A copy of the relation/value asserted by the proposal, NOT the reviewer's answer.
    resultat_annonce: Annotated[str, Field(min_length=1, max_length=100)]


class CalculRevu(ContratRevue):
    reference: Annotated[str, Field(pattern=r"^p[0-9]{1,3}$")]
    operation: Literal["comparaison", "pourcentage", "ecart_relatif", "difference"]
    gauche: Annotated[str, Field(pattern=r"^[nc][0-9]{1,3}$")]
    droite: Annotated[str, Field(pattern=r"^[nc][0-9]{1,3}$")]
    resultat_annonce: Annotated[str, Field(min_length=1, max_length=100)]


class Revue(ContratRevue):
    examens: Annotated[list[Ecart], Field(max_length=48)]
    calculs: Annotated[list[CalculRevu], Field(max_length=4)]
    confiance_max: Literal["faible", "moyenne"]
    preuves_suffisantes: bool = Field(strict=True)


class VerificationImpossible(ValueError):
    """A safe reason code only: never include original evidence in exceptions."""


_NOMBRE = r"[+-]?(?:[0-9]{1,3}(?:[ \u00a0\u202f][0-9]{3})+|[0-9]+)(?:[.,][0-9]+)?"
_SCALAIRE = re.compile(rf"(?P<valeur>{_NOMBRE})\s*(?P<unite>%|[A-Za-zµ]+)?")
_UNITES: dict[str, tuple[str, Decimal]] = {
    "": ("nombre", Decimal(1)),
    "%": ("proportion", Decimal("0.01")),
    "ms": ("duree", Decimal("0.001")),
    "s": ("duree", Decimal(1)),
    "sec": ("duree", Decimal(1)),
    "second": ("duree", Decimal(1)),
    "seconds": ("duree", Decimal(1)),
    "seconde": ("duree", Decimal(1)),
    "secondes": ("duree", Decimal(1)),
    "min": ("duree", Decimal(60)),
    "minute": ("duree", Decimal(60)),
    "minutes": ("duree", Decimal(60)),
    "h": ("duree", Decimal(3600)),
    "heure": ("duree", Decimal(3600)),
    "heures": ("duree", Decimal(3600)),
    "hour": ("duree", Decimal(3600)),
    "hours": ("duree", Decimal(3600)),
    "Ki": ("octets", Decimal(1024)),
    "Mi": ("octets", Decimal(1024**2)),
    "Gi": ("octets", Decimal(1024**3)),
    "B": ("octets", Decimal(1)),
    "KiB": ("octets", Decimal(1024)),
    "MiB": ("octets", Decimal(1024**2)),
    "GiB": ("octets", Decimal(1024**3)),
    "kB": ("octets", Decimal(1000)),
    "MB": ("octets", Decimal(1000**2)),
    "GB": ("octets", Decimal(1000**3)),
}


def _decimal(texte: str) -> Decimal:
    # A comma followed by three digits can mean a decimal or a thousands group.
    # Do not silently choose a locale for bilingual observations.
    if re.fullmatch(r"[+-]?[1-9][0-9]{0,2},[0-9]{3}", texte):
        raise VerificationImpossible("notation_numerique_ambigue")
    try:
        valeur = Decimal(re.sub(r"[ \u00a0\u202f]", "", texte).replace(",", "."))
    except InvalidOperation:
        raise VerificationImpossible("nombre_non_supporte") from None
    if not valeur.is_finite() or abs(valeur) > Decimal("1e18"):
        raise VerificationImpossible("nombre_hors_limites")
    if len(valeur.as_tuple().digits) > 24:
        raise VerificationImpossible("precision_non_supportee")
    return valeur


def _lire_operande(operande: Operande, original: str) -> tuple[Decimal, str]:
    contexte, valeur = operande.contexte, operande.valeur
    if contexte not in original or contexte.count(valeur) != 1:
        raise VerificationImpossible("operande_non_source")
    # Prevent a cited "2" from selecting the tail of "12" or a substring of a timestamp.
    suffixes = []
    for occurrence in re.finditer(re.escape(contexte), original):
        position = occurrence.start() + contexte.index(valeur)
        avant, apres = original[:position], original[position + len(valeur) :]
        if not (
            (avant and re.search(r"[\w.,+-]$|[0-9]:$", avant))
            or (apres and re.match(r"(?:[\w:%]|[.,+-][0-9])", apres))
        ):
            suffixes.append(apres)
    if not suffixes:
        raise VerificationImpossible("operande_tronque")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})", valeur):
        try:
            date = datetime.fromisoformat(valeur)
        except ValueError:
            raise VerificationImpossible("horodatage_invalide") from None
        return Decimal(str(date.timestamp())), "instant"
    correspondance = _SCALAIRE.fullmatch(valeur)
    if not correspondance:
        raise VerificationImpossible("format_operande_non_supporte")
    unite = correspondance["unite"] or ""
    if unite not in _UNITES:
        raise VerificationImpossible("unite_non_supportee")
    dimension, facteur = _UNITES[unite]
    # Omitting a known unit would make 2 hours comparable to 80 minutes as bare counts.
    if not unite and all(
        (suffixe := re.match(r"\s*(%|[A-Za-zµ]+)", apres)) and suffixe[1] in _UNITES
        for apres in suffixes
    ):
        raise VerificationImpossible("unite_omise")
    with localcontext() as contexte_decimal:
        contexte_decimal.prec = 40
        return _decimal(correspondance["valeur"]) * facteur, dimension


def verifier_calcul(calcul: Calcul, original: str) -> tuple[str, bool]:
    """Compute a declared comparison using literal operands, without evaluating code.

    Same-dimensional numeric inputs can still describe incomparable populations.
    No inference of causality, statistical significance or shared clock is made.
    """
    gauche, dimension = _lire_operande(calcul.gauche, original)
    droite, autre_dimension = _lire_operande(calcul.droite, original)
    rendu, conforme, _ = _calculer(
        calcul.operation, (gauche, dimension), (droite, autre_dimension), calcul.resultat_annonce
    )
    empreinte = hashlib.sha256(
        (calcul.gauche.contexte + "\0" + calcul.droite.contexte).encode()
    ).hexdigest()[:16]
    return f"{rendu} [ref {empreinte}]", conforme


def _calculer(
    operation: str,
    valeur_gauche: tuple[Decimal, str],
    valeur_droite: tuple[Decimal, str],
    resultat_annonce: str,
) -> tuple[str, bool, tuple[Decimal, str] | None]:
    gauche, dimension = valeur_gauche
    droite, autre_dimension = valeur_droite
    if dimension != autre_dimension:
        raise VerificationImpossible("dimensions_incompatibles")
    reutilisable = None
    with localcontext() as contexte:
        contexte.prec = 40
        if operation == "comparaison":
            resultat = "<" if gauche < droite else ">" if gauche > droite else "="
            conforme = resultat == resultat_annonce.strip()
        else:
            if dimension == "instant" and operation != "difference":
                raise VerificationImpossible("rapport_horodatages_interdit")
            if operation in {"pourcentage", "ecart_relatif"}:
                if droite == 0:
                    raise VerificationImpossible("denominateur_nul")
                nombre = gauche if operation == "pourcentage" else gauche - droite
                nombre = nombre / droite * 100
                unite = "%"
                reutilisable = (nombre / 100, "proportion")
            else:
                nombre = gauche - droite
                reutilisable = (nombre, "duree" if dimension == "instant" else dimension)
                unite = {"duree": "s", "instant": "s", "octets": "B"}.get(dimension, "")
                if dimension == "proportion":
                    nombre *= 100
                    unite = "points de pourcentage"
            resultat = f"{nombre.normalize():f} {unite}".strip()
            annonce = resultat_annonce.strip()
            # The claim is a numeric value in the output unit specified by the contract.
            if not re.fullmatch(_NOMBRE, annonce):
                raise VerificationImpossible("resultat_annonce_invalide")
            # Exact arithmetic: never turn a positive rate into an asserted zero by rounding.
            decimal_annonce = _decimal(annonce)
            conforme = nombre == decimal_annonce
    rendu = f"{operation} : gauche={gauche}, droite={droite} ({dimension}) → {resultat}"
    return rendu, conforme, reutilisable


def indexer_propositions(
    extrait: Extraction, diagnostic: Diagnostic, *, constat_garde_ajoute: bool = False
) -> list[dict[str, str]]:
    """Bind reviewer references to exact application-owned fields, not copied prose."""
    propositions: list[dict[str, str]] = []
    for objet, instance, champs in (
        ("extraction", extrait, ("signature_technique", "symptomes", "composants")),
        ("diagnostic", diagnostic, ("cause_probable", "elements_manquants", "actions_proposees")),
    ):
        for champ in champs:
            valeur = getattr(instance, champ)
            modalite = (
                "question_ou_information_requise"
                if champ == "elements_manquants"
                else "action_future_soumise_a_approbation"
                if champ == "actions_proposees"
                else "conclusion_a_qualifier"
                if champ == "cause_probable"
                else "fait_allegue_par_extraction"
            )
            for indice, texte in enumerate(valeur if isinstance(valeur, list) else [valeur]):
                # The caller has just run the source guard and knows that it appended
                # this field. No text matching or model-supplied provenance is trusted.
                if (
                    constat_garde_ajoute
                    and champ == "elements_manquants"
                    and indice == len(diagnostic.elements_manquants) - 1
                ):
                    continue
                propositions.append(
                    {
                        "reference": f"p{len(propositions)}",
                        "champ": f"{objet}.{champ}",
                        "modalite": modalite,
                        "texte": texte,
                    }
                )
    if len(propositions) > 48:
        raise VerificationImpossible("trop_de_propositions")
    return propositions


def indexer_operandes(original: str) -> tuple[list[dict[str, str]], dict[str, tuple[Decimal, str]]]:
    """Enumerate supported literal quantities; never infer a metric or its meaning."""
    unites = "|".join(re.escape(u) for u in sorted(_UNITES, key=len, reverse=True) if u)
    date = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})"
    expression = re.compile(
        rf"(?<![\w.,+-])(?:{date}|{_NOMBRE}(?:\s*(?:{unites})(?!\w))?)(?![\w:%]|[.,+-][0-9])"
    )
    registre: list[dict[str, str]] = []
    valeurs: dict[str, tuple[Decimal, str]] = {}
    for occurrence in expression.finditer(original):
        litteral = occurrence[0]
        try:
            valeur = _lire_operande(Operande(contexte=litteral, valeur=litteral), original)
        except VerificationImpossible, ValidationError:
            continue  # Unsupported syntax remains visible in the original; it is not coerced.
        reference = f"n{len(registre)}"
        if len(registre) >= 64:
            raise VerificationImpossible("trop_de_quantites")
        registre.append(
            {
                "reference": reference,
                "litteral": litteral,
                "contexte": original[max(0, occurrence.start() - 45) : occurrence.end() + 45],
                "dimension": valeur[1],
            }
        )
        valeurs[reference] = valeur
    return registre, valeurs


def extraction_retenue(extrait: Extraction, diagnostic: Diagnostic) -> Extraction:
    if diagnostic.qualite and diagnostic.qualite.extraction_ecartee:
        return extrait.model_copy(
            update={
                "signature_technique": "Résumé de recherche écarté par la revue de cohérence.",
                "symptomes": [],
                "composants": [],
            }
        )
    return extrait


def verifier_diagnostic(
    diagnostic: Diagnostic,
    extrait: Extraction,
    original: str | None,
    budget: Budget,
    *,
    appel: Callable[..., ReponseLLM],
    nombre_actions_ecartees: int = 0,
) -> Diagnostic:
    """One local call under the ordinary budget; no silent unreviewed fallback."""
    debut = time.monotonic()
    avant_entree, avant_sortie = budget.tokens_entree, budget.tokens_sortie
    qualite = QualiteDiagnostic(statut="abstention")
    rejet = True
    plafond = Confiance.FAIBLE
    try:
        if not original:
            raise VerificationImpossible("observations_originales_absentes")
        if type(nombre_actions_ecartees) is not int or nombre_actions_ecartees < 0:
            raise VerificationImpossible("contexte_garde_source_invalide")
        propositions = indexer_propositions(
            extrait, diagnostic, constat_garde_ajoute=nombre_actions_ecartees > 0
        )
        par_reference = {p["reference"]: p for p in propositions}
        registre, valeurs = indexer_operandes(original)
        schema = Revue.model_json_schema()
        schema["$defs"]["Ecart"]["properties"]["reference"]["enum"] = list(par_reference)
        schema["$defs"]["CalculRevu"]["properties"]["reference"]["enum"] = list(par_reference)
        reponse = appel(
            alias=config.ALIAS_RAISONNEMENT,
            messages=prompts.messages_revue(
                original,
                propositions,
                registre,
                budget.sources_lues.get(diagnostic.runbook_source or "", ""),
                nombre_actions_ecartees=nombre_actions_ecartees,
            ),
            classification=Classification.CONFIDENTIEL,
            budget=budget,
            tache="revue_coherence",
            max_tokens=2500,
            schema_json=schema,
        )
        revue = Revue.model_validate(extraire_json(reponse.contenu))
        # The wrapper enforces observed token/time caps too, including after this final call.
        budget.verifier_avant_llm()
        references = [e.reference for e in revue.examens]
        if len(references) != len(set(references)) or set(references) != set(par_reference):
            raise VerificationImpossible("couverture_revue_incomplete_ou_dupliquee")
        rejet = not revue.preuves_suffisantes
        if rejet:
            qualite.ecarts.append("preuves_insuffisantes")
        for ecart in revue.examens:
            if ecart.reference not in par_reference:
                raise VerificationImpossible("reference_proposition_invalide")
            if ecart.nature == "aucun":
                continue
            champ = par_reference[ecart.reference]["champ"]
            qualite.ecarts.append(f"{champ}:{ecart.nature}")
            if champ.startswith("extraction."):
                qualite.extraction_ecartee = True
            else:
                rejet = True
        for indice, calcul in enumerate(revue.calculs):
            if calcul.reference not in par_reference:
                raise VerificationImpossible("reference_proposition_invalide")
            if calcul.gauche not in valeurs or calcul.droite not in valeurs:
                raise VerificationImpossible("reference_operande_invalide")
            champ = par_reference[calcul.reference]["champ"]
            rendu, conforme, reutilisable = _calculer(
                calcul.operation,
                valeurs[calcul.gauche],
                valeurs[calcul.droite],
                calcul.resultat_annonce,
            )
            empreinte = hashlib.sha256(original.encode()).hexdigest()[:16]
            qualite.calculs.append(
                f"c{indice} : {rendu} [ref {empreinte}:{calcul.gauche},{calcul.droite}]"
            )
            if reutilisable is not None:
                valeurs[f"c{indice}"] = reutilisable
            if not conforme:
                qualite.ecarts.append(f"{champ}:calcul_contredit")
                if champ.startswith("extraction."):
                    qualite.extraction_ecartee = True
                else:
                    rejet = True
        plafond = Confiance(revue.confiance_max)
    except (VerificationImpossible, ValidationError, ErreurPasserelle) as erreur:
        rejet = True
        qualite.ecarts.append(
            str(erreur) if isinstance(erreur, VerificationImpossible) else "revue_indisponible"
        )
        # An unavailable review cannot leave the unverified extraction displayed as fact.
        qualite.extraction_ecartee = True
    qualite.latence_ms = round((time.monotonic() - debut) * 1000)
    qualite.tokens_entree = budget.tokens_entree - avant_entree
    qualite.tokens_sortie = budget.tokens_sortie - avant_sortie
    if rejet:
        return Diagnostic(
            cause_probable=(
                "Abstention : la cohérence de la proposition n'a pas pu être retenue. "
                "Aucun diagnostic causal ni procédure n'est livré. "
                "Comparer les observations originales et les sources avec un humain."
            ),
            confiance=Confiance.FAIBLE,
            elements_manquants=[
                "Qualification de la proposition : " + ", ".join(qualite.ecarts),
                qualite.limite,
            ],
            qualite=qualite,
        )
    qualite.statut = "revue_ia_sans_ecart_bloquant"
    ordre = {Confiance.FAIBLE: 0, Confiance.MOYENNE: 1, Confiance.HAUTE: 2}
    return diagnostic.model_copy(
        update={
            "confiance": min((diagnostic.confiance, plafond), key=ordre.__getitem__),
            "qualite": qualite,
        }
    )
