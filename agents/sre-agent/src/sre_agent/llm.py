"""Point de passage unique vers la passerelle LiteLLM.

Tout appel LLM de l'agent traverse `appeler_llm`. C'est ce qui rend le
cloisonnement vérifiable : il y a un seul endroit à lire pour savoir si
de la donnée client peut sortir, et un seul endroit à modifier pour que
ce ne soit plus vrai. Un appel direct à httpx ailleurs dans le paquet
serait un défaut d'architecture, pas une optimisation.

Trois barrières, dans cet ordre :
1. Garde applicative : classification CONFIDENTIEL + alias frontière
   lève FuiteConfidentielle avant tout accès réseau.
2. Clé virtuelle : une charge confidentielle est envoyée avec
   CONFIDENTIAL_KEY, restreinte côté passerelle à local et local-embed.
3. Passerelle : aucune bascule n'est configurée depuis `local`, une
   erreur locale n'a donc pas de repli vers la frontière.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx
from opentelemetry import propagate
from opentelemetry.trace import SpanKind, Status, StatusCode

from . import config, tracage
from .budget import Budget
from .config import ALIAS_CONNUS, ALIAS_LOCAUX, Classification


class FuiteConfidentielle(RuntimeError):
    """Un appel confidentiel visait un alias frontière. Rien n'a été envoyé."""


class ErreurPasserelle(RuntimeError):
    """La passerelle a refusé ou n'a pas répondu."""


@dataclass
class ReponseLLM:
    contenu: str
    appels_outils: list[dict[str, Any]] = field(default_factory=list)
    message: dict[str, Any] = field(default_factory=dict)
    cout_usd: float = 0.0
    tokens_entree: int = 0
    tokens_sortie: int = 0
    motif_arret: str = ""


def _cout_depuis_entetes(entetes: httpx.Headers) -> float:
    """Lit le coût rapporté par la passerelle.

    La passerelle est l'autorité sur le prix : l'agent ne tient pas de
    table tarifaire, ce qui lui éviterait de toute façon de connaître un
    nom de modèle. L'en-tête plat est absent quand le coût est nul.
    """
    for nom in ("x-litellm-response-cost", "x-litellm-response-cost-original"):
        brut = entetes.get(nom)
        if brut:
            try:
                return float(brut)
            except ValueError:
                continue
    return 0.0


def _systeme_depuis_entetes(entetes: httpx.Headers) -> str:
    """Déduit gen_ai.system de ce que la passerelle rapporte avoir servi.

    Valeur lue à l'exécution, jamais écrite dans le code : la règle 1 du
    CLAUDE.md interdit d'y inscrire un nom de fournisseur, pas d'observer
    celui que la passerelle a choisi.
    """
    nom = entetes.get("x-litellm-model-name", "")
    return nom.split("/", 1)[0] if "/" in nom else (nom or "inconnu")


def appeler_llm(
    *,
    alias: str,
    messages: list[dict[str, Any]],
    classification: Classification,
    budget: Budget,
    tache: str,
    outils: list[dict[str, Any]] | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.0,
    format_json: bool = False,
) -> ReponseLLM:
    """Appelle un modèle par son alias, sous garde de cloisonnement.

    Args:
        alias: alias de passerelle. Jamais un nom de modèle fournisseur.
        classification: nature de la donnée transportée par `messages`.
        budget: compteurs de l'exécution, mis à jour ici.
        tache: valeur de ambicrafted.task.type sur la span.
    """
    if alias not in ALIAS_CONNUS:
        raise ErreurPasserelle(
            f"Alias inconnu : {alias!r}. Alias déclarés : {sorted(ALIAS_CONNUS)}."
        )

    # --- Barrière 1 : garde applicative, avant tout accès réseau --------
    if classification is Classification.CONFIDENTIEL and alias not in ALIAS_LOCAUX:
        raise FuiteConfidentielle(
            f"Refus : charge classée {classification.value} vers l'alias frontière "
            f"{alias!r}. Une donnée d'alerte brute ne quitte pas la machine. "
            f"Alias autorisés pour cette classification : {sorted(ALIAS_LOCAUX)}."
        )

    budget.verifier_avant_llm()

    corps: dict[str, Any] = {
        "model": alias,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if outils:
        corps["tools"] = outils
        corps["tool_choice"] = "auto"
    if format_json:
        corps["response_format"] = {"type": "json_object"}

    with tracage.tracer().start_as_current_span(
        f"llm.{tache}", kind=SpanKind.CLIENT
    ) as span:
        span.set_attribute(tracage.ATTR_CLASSIFICATION, classification.value)
        span.set_attribute(tracage.ATTR_TYPE_TACHE, tache)
        span.set_attribute(tracage.ATTR_ALIAS, alias)
        span.set_attribute("gen_ai.operation.name", "chat")
        span.set_attribute("gen_ai.request.model", alias)
        span.set_attribute("gen_ai.request.max_tokens", max_tokens)
        span.set_attribute("gen_ai.request.temperature", temperature)

        entetes = {
            # --- Barrière 2 : clé restreinte pour le confidentiel
            "Authorization": f"Bearer {config.cle(classification)}",
            "Content-Type": "application/json",
        }
        # Contexte de trace W3C (traceparent) : la passerelle rattache ses
        # propres spans sous cette span llm.*, et un appel LLM n'est plus
        # deux traces disjointes (ADR 0005). Injecté ici, donc après la
        # barrière 1 : une charge refusée n'a jamais d'en-tête construit.
        # Sans span active (traçage coupé), le propagateur n'écrit rien.
        propagate.inject(entetes)

        try:
            reponse = httpx.post(
                f"{config.LITELLM_BASE_URL.rstrip('/')}/chat/completions",
                headers=entetes,
                json=corps,
                timeout=config.TIMEOUT_LLM_S,
            )
        except httpx.HTTPError as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise ErreurPasserelle(
                f"Passerelle injoignable sur {config.LITELLM_BASE_URL} : "
                f"{type(e).__name__} : {e}"
            ) from e

        cout = _cout_depuis_entetes(reponse.headers)
        span.set_attribute("gen_ai.system", _systeme_depuis_entetes(reponse.headers))
        span.set_attribute(tracage.ATTR_COUT, cout)

        if reponse.status_code != 200:
            span.set_status(Status(StatusCode.ERROR, f"HTTP {reponse.status_code}"))
            raise ErreurPasserelle(
                f"Passerelle : HTTP {reponse.status_code} sur l'alias {alias!r} — "
                f"{reponse.text[:400]}"
            )

        donnees = reponse.json()
        usage = donnees.get("usage") or {}
        entree = int(usage.get("prompt_tokens") or 0)
        sortie = int(usage.get("completion_tokens") or 0)

        choix = (donnees.get("choices") or [{}])[0]
        message = choix.get("message") or {}

        span.set_attribute("gen_ai.response.model", str(donnees.get("model", alias)))
        span.set_attribute("gen_ai.usage.input_tokens", entree)
        span.set_attribute("gen_ai.usage.output_tokens", sortie)
        span.set_attribute(
            "gen_ai.response.finish_reasons", [str(choix.get("finish_reason", ""))]
        )

        resultat = ReponseLLM(
            contenu=message.get("content") or "",
            appels_outils=list(message.get("tool_calls") or []),
            message=message,
            cout_usd=cout,
            tokens_entree=entree,
            tokens_sortie=sortie,
            motif_arret=str(choix.get("finish_reason") or ""),
        )
        span.set_attribute("gen_ai.response.tool_calls", len(resultat.appels_outils))

        # Imputé dans la span : un dépassement reste visible dans la trace.
        budget.consommer_llm(cout, entree, sortie)
        span.set_attribute("ambicrafted.budget.spent_usd", round(budget.cout_usd, 6))

    return resultat


_BLOC_JSON = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extraire_json(texte: str) -> dict[str, Any]:
    """Extrait un objet JSON d'une réponse de modèle.

    Les modèles à raisonnement encadrent volontiers leur JSON de prose ou
    de clôtures Markdown. Plutôt que d'exiger une sortie propre par le
    prompt, ce qui n'est jamais garanti, on tolère les trois formes
    rencontrées et on échoue clairement si aucune ne s'applique.
    """
    candidats: list[str] = []
    if m := _BLOC_JSON.search(texte):
        candidats.append(m.group(1))
    debut, fin = texte.find("{"), texte.rfind("}")
    if debut != -1 and fin > debut:
        candidats.append(texte[debut : fin + 1])
    candidats.append(texte)

    for candidat in candidats:
        try:
            valeur = json.loads(candidat.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(valeur, dict):
            return valeur

    raise ErreurPasserelle(
        f"Réponse du modèle non exploitable comme JSON : {texte[:300]!r}"
    )
