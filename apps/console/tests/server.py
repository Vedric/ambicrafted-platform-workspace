"""Disposable real HTTP API for browser tests; inference is deliberately simulated.

This test-only entrypoint never reads the workstation's .env or opens its state.
The normal application has no switch enabling this deterministic engine.
"""

import asyncio
import contextlib
import json
import os
import tempfile
from pathlib import Path

import plateforme.app as application_module
import uvicorn
from plateforme.app import creer_app
from plateforme.config import Parametres
from plateforme.depot import Conflit, maintenant
from plateforme.moteur import Moteur
from plateforme.securite import hacher_mot_de_passe
from plateforme.services import Services

WEB = Path(__file__).resolve().parents[1] / "dist"
DIAGNOSTIC = {
    "cause_probable": "Saturation des connexions dans cet exercice synthétique.",
    "confiance": "moyenne",
    "runbook_source": "postgres.md",
    "actions_proposees": ["Vérifier le nombre de connexions avant toute intervention."],
    "elements_manquants": ["Confirmer les métriques de l'incident réel."],
}


class ParametresTest(Parametres):
    @property
    def web(self) -> Path:
        return WEB


class MoteurDeterministe(Moteur):
    async def executer(self, identifiant: str, decision: bool | None) -> None:
        analyse = self.depot.obtenir(identifiant)
        with contextlib.suppress(Conflit):
            self.depot.changer(
                identifiant, "en_cours", attendus={"en_file", "decision"}
            )
            self.depot.progression(identifiant, "demarrage")
            alerte = self.alertes.pop(identifiant, "")
            await asyncio.sleep(4 if alerte.startswith("LENT") else 0.12)
            self.depot.progression(identifiant, "modele")
            self.depot.progression(identifiant, "outil")
            statut = (
                "en_attente_humain"
                if decision is None
                else "complet"
                if decision
                else "rejete_par_humain"
            )
            rapport = {
                "statut": statut,
                "diagnostic": DIAGNOSTIC if decision else None,
                "classification": {
                    "connue": True,
                    "urgence": 3,
                    "justification": "Données de test synthétiques.",
                },
                "message": json.dumps(DIAGNOSTIC, ensure_ascii=False)
                if decision is None
                else "Diagnostic refusé."
                if not decision
                else "Diagnostic approuvé.",
                "outils_appeles": ["lire_runbook"],
                "budget": {"appels_llm": 2, "cout_usd": 0},
            }
            if analyse["mode"] == "operation":
                statut = "complet"
                rapport = {
                    "statut": statut,
                    "message": "Opération simulée pour le test navigateur.",
                }
            self.depot.changer(
                identifiant,
                statut,
                attendus={"en_cours"},
                rapport=rapport,
                duree_s=0.12,
            )
            self.depot.progression(identifiant, "termine")


async def sante(_):
    return {
        "ok": True,
        "services": [
            {
                "id": "passerelle",
                "nom": "Passerelle locale",
                "ok": True,
                "latence_ms": 5,
            },
            {"id": "index", "nom": "Mémoire vectorielle", "ok": True, "latence_ms": 2},
        ],
        "modeles": [{"nom": "local", "taille": 1024**3}],
        "index": {"points": 3, "statut": "green"},
    }


async def cibles(_):
    return [
        {
            "nom": "test-local",
            "sante": "up",
            "dernier_scrape": maintenant(),
            "duree_s": 0.01,
        }
    ]


async def semantique(_, requete):
    return [
        {
            "score": 0.71,
            "donnees": {
                "fichier": "postgres.md",
                "texte": "Vérifier le nombre de connexions avant toute intervention.",
            },
        }
    ]


async def dialoguer_simule(_, messages):
    await asyncio.sleep(0.08)
    return {
        "texte": "Réponse synthétique : ouvrez Analyses pour examiner un incident avec ses sources.",
        "local": True,
        "actions_executees": False,
    }


def main():
    password = os.environ.pop("PLATFORM_E2E_PASSWORD", "")
    cle = os.environ.pop("PLATFORM_E2E_KEY", "")
    if len(password) < 32 or len(cle) < 32 or not (WEB / "index.html").is_file():
        raise SystemExit(
            "Build the console and provide the ephemeral test password first."
        )
    with tempfile.TemporaryDirectory(prefix="ambicrafted-e2e-") as temporaire:
        racine = Path(temporaire)
        corpus = racine / "runbooks"
        corpus.mkdir()
        (corpus / "postgres.md").write_text(
            "# PostgreSQL : connexions\n\n## Diagnostic\n\nVérifier le nombre de connexions avant toute intervention.\n",
            encoding="utf-8",
        )
        p = ParametresTest(
            racine=racine,
            etat=racine / "etat",
            cle=cle,
            mot_de_passe=hacher_mot_de_passe(password),
            port=8789,
        )
        Services.sante = sante
        Services.cibles = cibles
        Services.semantique = semantique
        application_module.dialoguer = dialoguer_simule
        app = creer_app(p, moteur_classe=MoteurDeterministe)
        uvicorn.run(
            app, host="127.0.0.1", port=8789, access_log=False, log_level="error"
        )


if __name__ == "__main__":
    main()
