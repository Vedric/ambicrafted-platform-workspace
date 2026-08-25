"""Budgets d'exécution : itérations et argent.

Un budget n'est pas une consigne donnée au modèle, c'est un compteur tenu
par le code appelant. Le modèle ne peut ni le lire ni le modifier : il
peut seulement se le voir opposer.

Les deux budgets lèvent la même exception, parce que la conduite à tenir
est la même : arrêt propre, escalade humaine, jamais de dégradation
silencieuse ni de réponse tronquée présentée comme complète.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class BudgetEpuise(RuntimeError):
    """Un plafond a été atteint. L'exécution s'arrête, un humain reprend."""

    def __init__(self, motif: str, detail: str) -> None:
        super().__init__(f"budget épuisé, escalade humaine requise : {motif} ({detail})")
        self.motif = motif
        self.detail = detail


@dataclass
class Budget:
    """Compteurs d'une exécution. Un objet par alerte, jamais partagé."""

    max_appels_outils: int
    max_cout_usd: float

    appels_outils: int = 0
    cout_usd: float = 0.0
    appels_llm: int = 0
    tokens_entree: int = 0
    tokens_sortie: int = 0
    # Journal des dépassements évités, utile en post-mortem.
    historique: list[str] = field(default_factory=list)

    # --- Outils ----------------------------------------------------------

    def consommer_outil(self, nom: str) -> None:
        """Décompte un appel d'outil. Lève AVANT de l'exécuter."""
        if self.appels_outils >= self.max_appels_outils:
            raise BudgetEpuise(
                "plafond d'appels d'outils atteint",
                f"{self.appels_outils}/{self.max_appels_outils}, refus de '{nom}'",
            )
        self.appels_outils += 1
        self.historique.append(f"outil #{self.appels_outils} : {nom}")

    def outils_restants(self) -> int:
        return max(0, self.max_appels_outils - self.appels_outils)

    # --- Argent ----------------------------------------------------------

    def verifier_avant_llm(self) -> None:
        """Refuse d'engager un appel LLM si le plafond est déjà atteint."""
        if self.cout_usd >= self.max_cout_usd:
            raise BudgetEpuise(
                "plafond monétaire atteint",
                f"{self.cout_usd:.4f}/{self.max_cout_usd:.2f} USD",
            )

    def consommer_llm(self, cout_usd: float, tokens_entree: int, tokens_sortie: int) -> None:
        """Impute le coût rapporté par la passerelle.

        Le contrôle est fait après coup : le coût exact d'un appel n'est
        connu qu'une fois la réponse reçue. Le dépassement est donc
        constaté, jamais prédit, et il interrompt le tour suivant.
        """
        self.appels_llm += 1
        self.cout_usd += cout_usd
        self.tokens_entree += tokens_entree
        self.tokens_sortie += tokens_sortie
        if self.cout_usd > self.max_cout_usd:
            raise BudgetEpuise(
                "plafond monétaire dépassé",
                f"{self.cout_usd:.4f}/{self.max_cout_usd:.2f} USD "
                f"après {self.appels_llm} appels LLM",
            )

    def resume(self) -> dict[str, float | int]:
        return {
            "appels_outils": self.appels_outils,
            "max_appels_outils": self.max_appels_outils,
            "appels_llm": self.appels_llm,
            "cout_usd": round(self.cout_usd, 6),
            "max_cout_usd": self.max_cout_usd,
            "tokens_entree": self.tokens_entree,
            "tokens_sortie": self.tokens_sortie,
        }
