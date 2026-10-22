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
from uuid import NAMESPACE_URL, uuid5

import plateforme.app as application_module
import plateforme.conversation_routes as conversation_module
import uvicorn
from plateforme.app import creer_app
from plateforme.config import Parametres
from plateforme.depot import Conflit, maintenant
from plateforme.moteur import Moteur
from plateforme.securite import hacher_mot_de_passe
from plateforme.services import Services

WEB = Path(os.environ.get("PLATFORM_E2E_WEB", Path(__file__).resolve().parents[1] / "dist"))
DIAGNOSTIC = {
    "cause_probable": "Connection pool exhausted in this synthetic exercise.",
    "confiance": "moyenne",
    "runbook_source": "postgres.md",
    "actions_proposees": ["Check the connection count before intervening."],
    "elements_manquants": ["Confirm the actual incident metrics."],
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
            await asyncio.sleep(4 if alerte.startswith("SLOW") else 0.12)
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
                    "justification": "Synthetic test data.",
                },
                "message": json.dumps(DIAGNOSTIC, ensure_ascii=False)
                if decision is None
                else "Diagnosis rejected."
                if not decision
                else "Diagnosis approved.",
                "outils_appeles": ["lire_runbook"],
                "budget": {"appels_llm": 2, "cout_usd": 0},
            }
            if analyse["mode"] == "operation":
                statut = "complet"
                rapport = {
                    "statut": statut,
                    "message": "Operation simulated for the browser test.",
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
                "id": "litellm",
                "nom": "AI gateway",
                "ok": True,
                "latence_ms": 5,
            },
            {"id": "qdrant", "nom": "Vector memory", "ok": True, "latence_ms": 2},
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
                "texte": "Check the connection count before intervening.",
            },
        }
    ]


async def dialoguer_simule(_, messages, langue="en"):
    await asyncio.sleep(0.08)
    return {
        "texte": "Réponse simulée : ouvrez Analyses pour examiner un incident avec ses sources." if langue == "fr" else "Synthetic reply: open Analyses to investigate an incident with its sources.",
        "local": True,
        "actions_executees": False,
    }


async def flux_simule(p, messages, langue="en", vocal=False):
    result = await dialoguer_simule(p, messages, langue)
    for word in result["texte"].split(" "):
        yield {"type": "token", "text": word + " "}
    result["texte"] += " "
    yield {"type": "done", **result}


async def document_simule(p, messages, langue, format, conversation, operation, sources):
    # Only inference is simulated: the real route validates, authenticates,
    # persists, replays and exports the document in disposable SQLite state.
    fixtures = json.loads((Path(__file__).parent / "fixtures/documents.json").read_text())
    # Guide-only examples retain the same route, validation and real persistence.
    payload = json.dumps(messages, ensure_ascii=False).lower()
    if "synthetic guide" in payload or "guide fictif" in payload:
        fixtures = json.loads((Path(__file__).parent / "fixtures/guides-documents.json").read_text())[langue]
    artifact = fixtures[format]
    artifact["id"] = str(uuid5(NAMESPACE_URL, f"ambicrafted:{conversation}:{operation}"))
    artifact["sources"] = sources
    await asyncio.sleep(0.08)
    return {"type": "done", "texte": artifact["summary"], "local": True,
            "actions_executees": False, "artefacts": [artifact]}


conversation_module.generer_artefact = document_simule
conversation_module.flux_dialogue = flux_simule


async def preparer_simule(_):
    await asyncio.sleep(0.01)


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
            "# PostgreSQL: connections\n\n## Diagnosis\n\nCheck the connection count before intervening.\n",
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
        application_module.preparer_dialogue = preparer_simule
        app = creer_app(p, moteur_classe=MoteurDeterministe)
        limiter = app.state.auth.limiter

        def limiter_dialogue_fixture(groupe, maximum=5, intervalle=60):
            # Independent browser journeys share this disposable server. Keep
            # the real limiter and eight-request bound, but compress its dialogue
            # window to one second. Production's 60-second guard is qualified
            # separately by test_production_dialogue_rate_limit_and_recovery.
            limiter(groupe, maximum, 1 if groupe == "dialogue" else intervalle)

        app.state.auth.limiter = limiter_dialogue_fixture
        uvicorn.run(
            app, host="127.0.0.1", port=8789, access_log=False, log_level="error"
        )


if __name__ == "__main__":
    main()
