"""Run budgets: iterations, reported money and observed tokens.

A budget is not an instruction handed to the model, it is a counter held
by the calling code. The model can neither read it nor change it: it can
only have it held against it.

The ceilings raise the same exception, because the response is the same:
clean stop, human escalation, never a silent degradation nor a truncated
answer passed off as complete.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from . import config


class BudgetEpuise(RuntimeError):
    """A ceiling was reached. The run stops, a human takes over."""

    def __init__(self, motif: str, detail: str) -> None:
        super().__init__(f"budget épuisé, escalade humaine requise : {motif} ({detail})")
        self.motif = motif
        self.detail = detail


@dataclass
class Budget:
    """Counters for one run. One object per alert, never shared."""

    max_appels_outils: int
    max_cout_usd: float

    appels_outils: int = 0
    cout_usd: float = 0.0
    appels_llm: int = 0
    appels_llm_tentes: int = 0
    tokens_entree: int = 0
    tokens_sortie: int = 0
    appels_mesures_tokens: int = 0
    appels_mesures_entree: int = 0
    appels_mesures_sortie: int = 0
    appels_mesures_cout: int = 0
    max_tokens_total: int = field(default_factory=lambda: config.MAX_TOKENS_TOTAL)
    # Log of the overruns avoided, useful in a post-mortem.
    historique: list[str] = field(default_factory=list)
    outils_appeles: list[str] = field(default_factory=list)
    sources_lues: dict[str, str] = field(default_factory=dict)
    echeance: float = field(default_factory=lambda: time.monotonic() + config.MAX_DUREE_S)

    def __post_init__(self) -> None:
        if not math.isfinite(self.max_cout_usd) or self.max_cout_usd <= 0:
            raise ValueError("Le plafond monétaire doit être fini et strictement positif.")
        if self.max_appels_outils < 0:
            raise ValueError("Le plafond d'outils doit être positif ou nul.")
        if type(self.max_tokens_total) is not int or not 1 <= self.max_tokens_total <= 1_000_000:
            raise ValueError("Le plafond de jetons observés doit être entre 1 et 1000000.")

    def temps_restant(self) -> float:
        restant = self.echeance - time.monotonic()
        if restant <= 0:
            raise BudgetEpuise("durée maximale atteinte", "échéance de l'exécution")
        return restant

    # --- Tools -----------------------------------------------------------

    def consommer_outil(self, nom: str) -> None:
        """Charge one tool call. Raises BEFORE the call runs."""
        self.temps_restant()
        if self.appels_outils >= self.max_appels_outils:
            raise BudgetEpuise(
                "plafond d'appels d'outils atteint",
                f"{self.appels_outils}/{self.max_appels_outils}, refus de '{nom}'",
            )
        self.appels_outils += 1
        self.outils_appeles.append(nom)
        self.historique.append(f"outil #{self.appels_outils} : {nom}")

    def outils_restants(self) -> int:
        return max(0, self.max_appels_outils - self.appels_outils)

    # --- Money -----------------------------------------------------------

    def verifier_avant_llm(self) -> None:
        """Refuse to commit an LLM call if the ceiling is already reached."""
        self.temps_restant()
        if self.tokens_entree + self.tokens_sortie >= self.max_tokens_total:
            raise BudgetEpuise(
                "plafond de jetons observés atteint",
                f"{self.tokens_entree + self.tokens_sortie}/{self.max_tokens_total}",
            )
        if not math.isfinite(self.cout_usd) or self.cout_usd < 0:
            raise ValueError("Comptabilité monétaire invalide.")
        if self.cout_usd >= self.max_cout_usd:
            raise BudgetEpuise(
                "plafond monétaire atteint",
                f"{self.cout_usd:.4f}/{self.max_cout_usd:.2f} USD",
            )

    def consommer_llm(
        self, cout_usd: float | None, tokens_entree: int | None, tokens_sortie: int | None
    ) -> None:
        """Charge the cost reported by the gateway.

        The check happens after the fact: the exact cost of a call is only
        known once the response is in. An overrun is therefore observed,
        never predicted, and it stops the following turn.
        """
        if cout_usd is not None and (not math.isfinite(cout_usd) or cout_usd < 0):
            raise ValueError("Le coût doit être connu, fini et positif ou nul.")
        for valeur in (tokens_entree, tokens_sortie):
            if valeur is not None and (type(valeur) is not int or valeur < 0):
                raise ValueError("Un compteur de jetons doit être un entier positif ou nul.")
        self.appels_llm += 1
        if cout_usd is not None:
            self.cout_usd += cout_usd
            self.appels_mesures_cout += 1
        if tokens_entree is not None:
            self.tokens_entree += tokens_entree
            self.appels_mesures_entree += 1
        if tokens_sortie is not None:
            self.tokens_sortie += tokens_sortie
            self.appels_mesures_sortie += 1
        if tokens_entree is not None and tokens_sortie is not None:
            self.appels_mesures_tokens += 1
        if self.tokens_entree + self.tokens_sortie > self.max_tokens_total:
            raise BudgetEpuise(
                "plafond de jetons observés dépassé",
                f"{self.tokens_entree + self.tokens_sortie}/{self.max_tokens_total} "
                f"après {self.appels_llm} appels LLM",
            )
        if self.cout_usd > self.max_cout_usd:
            raise BudgetEpuise(
                "plafond monétaire dépassé",
                f"{self.cout_usd:.4f}/{self.max_cout_usd:.2f} USD "
                f"après {self.appels_llm} appels LLM",
            )

    def resume(self) -> dict[str, float | int | bool | None]:
        tentatives = max(self.appels_llm_tentes, self.appels_llm)
        entree = (
            self.tokens_entree
            if self.appels_mesures_entree or self.tokens_entree or not tentatives
            else None
        )
        sortie = (
            self.tokens_sortie
            if self.appels_mesures_sortie or self.tokens_sortie or not tentatives
            else None
        )
        disponible = bool(
            self.appels_mesures_entree
            or self.appels_mesures_sortie
            or self.tokens_entree
            or self.tokens_sortie
        )
        return {
            "appels_outils": self.appels_outils,
            "max_appels_outils": self.max_appels_outils,
            "appels_llm": self.appels_llm,
            "appels_llm_tentes": tentatives,
            "cout_usd": round(self.cout_usd, 6)
            if self.appels_mesures_cout or self.cout_usd or not tentatives
            else None,
            "cout_disponible": bool(self.appels_mesures_cout or self.cout_usd),
            "usage_cout_complet": tentatives == self.appels_mesures_cout,
            "appels_mesures_cout": self.appels_mesures_cout,
            "max_cout_usd": self.max_cout_usd,
            "tokens_entree": entree,
            "tokens_sortie": sortie,
            "tokens_total": self.tokens_entree + self.tokens_sortie
            if disponible or not tentatives
            else None,
            "tokens_disponibles": disponible,
            "usage_complet": tentatives == self.appels_mesures_tokens,
            "appels_mesures_tokens": self.appels_mesures_tokens,
            "appels_mesures_entree": self.appels_mesures_entree,
            "appels_mesures_sortie": self.appels_mesures_sortie,
            "max_tokens_total": self.max_tokens_total,
        }
