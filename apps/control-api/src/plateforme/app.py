"""Authenticated private HTTP API and same-origin console."""

import asyncio
import json
import shutil
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from . import __version__
from .assistant import dialoguer
from .catalogue import OUTILS
from .config import Parametres, enregistrer_secret
from .corpus import Corpus
from .depot import Conflit, Depot, Introuvable
from .moteur import ACTIFS, OPERATIONS, Moteur
from .preparation import Preparation
from .securite import (
    COOKIE,
    Authentification,
    FrontiereHTTP,
    hacher_mot_de_passe,
    verifier_mot_de_passe,
)
from .services import Services
from .voix import Voix


class Charge(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NouvelleAnalyse(Charge):
    titre: str = Field(min_length=1, max_length=100)
    alerte: str = Field(min_length=1, max_length=20_000)


class Decision(Charge):
    approuver: StrictBool


class Edition(Charge):
    contenu: str = Field(min_length=1, max_length=8000)
    empreinte: str = Field(default="", max_length=64)


class Connexion(Charge):
    ticket: str = Field(default="", max_length=128)
    mot_de_passe: str = Field(default="", max_length=128)


class MotDePasse(Charge):
    valeur: str = Field(min_length=14, max_length=128)


class Parole(Charge):
    langue: Literal["en", "fr"] = "en"
    texte: str = Field(min_length=1, max_length=2000)


class Audio(Charge):
    langue: Literal["en", "fr"] = "en"
    audio: str = Field(min_length=1, max_length=11_184_812)


class Message(Charge):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class Dialogue(Charge):
    langue: Literal["en", "fr"] = "en"
    messages: list[Message] = Field(min_length=1, max_length=8)


def creer_app(p: Parametres | None = None, moteur_classe=Moteur) -> FastAPI:
    p = p or Parametres.charger()
    depot, services = Depot(p.etat), Services(p)
    auth, corpus = Authentification(p, depot), Corpus(p.racine / "runbooks", depot)
    moteur = moteur_classe(p, depot)
    voix = Voix(p)
    preparation = Preparation(p, services, voix, corpus)
    flux_actifs = 0

    @asynccontextmanager
    async def cycle(app: FastAPI):
        await moteur.demarrer()
        try:
            voix.nettoyer_apres_arret()
            yield
        finally:
            await moteur.fermer()

    app = FastAPI(
        title="Ambicrafted",
        version=__version__,
        lifespan=cycle,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(FrontiereHTTP, parametres=p)
    app.state.depot, app.state.auth, app.state.moteur = depot, auth, moteur
    app.state.voix = voix
    app.state.preparation = preparation

    @app.exception_handler(RequestValidationError)
    async def validation(request, erreur):
        return JSONResponse(
            {"detail": "Données invalides : vérifier les champs et leurs limites."}, status_code=422
        )

    @app.exception_handler(Conflit)
    async def conflit(request, erreur):
        return JSONResponse({"detail": str(erreur)}, status_code=409)

    @app.exception_handler(Introuvable)
    async def introuvable(request, erreur):
        return JSONResponse({"detail": str(erreur)}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalide(request, erreur):
        return JSONResponse({"detail": "Données ou configuration invalides."}, status_code=400)

    @app.exception_handler(OSError)
    async def indisponible(request, erreur):
        return JSONResponse({"detail": "Ressource locale indisponible."}, status_code=503)

    @app.get("/api/ping")
    async def ping():
        return {"statut": "disponible", "version": __version__}

    @app.get("/api/auth")
    async def session(request: Request):
        empreinte = auth.session(request.cookies.get(COOKIE, ""))
        return {
            "connecte": bool(empreinte),
            "mot_de_passe": bool(p.mot_de_passe),
            "csrf": auth.csrf(empreinte) if empreinte else None,
        }

    @app.post("/api/auth/ticket")
    async def ticket(request: Request):
        if auth.acteur(request, mutation=True) != "cli":
            raise HTTPException(403, "Commande réservée au CLI local.")
        return {"ticket": auth.ticket()}

    @app.post("/api/auth/connexion")
    async def connexion(request: Request, charge: Connexion):
        auth.verifier_origine(request)
        if charge.ticket:
            jeton = auth.echanger(charge.ticket)
        else:
            auth.limiter("connexion")
            if not verifier_mot_de_passe(charge.mot_de_passe, p.mot_de_passe):
                raise HTTPException(401, "Connexion refusée.")
            jeton = auth.creer_session()
        reponse = JSONResponse({"connecte": True})
        reponse.set_cookie(
            COOKIE, jeton, httponly=True, samesite="strict", max_age=p.duree_session, path="/"
        )
        return reponse

    @app.post("/api/auth/deconnexion")
    async def deconnexion(request: Request):
        auth.acteur(request, mutation=True)
        empreinte = auth.session(request.cookies.get(COOKIE, ""))
        with depot.connexion() as c:
            c.execute("DELETE FROM sessions WHERE empreinte=?", (empreinte,))
        reponse = JSONResponse({"connecte": False})
        reponse.delete_cookie(COOKIE)
        return reponse

    @app.put("/api/auth/mot-de-passe")
    async def mot_de_passe(request: Request, charge: MotDePasse):
        acteur = auth.acteur(request, mutation=True)
        valeur = await asyncio.to_thread(hacher_mot_de_passe, charge.valeur)
        enregistrer_secret(p.racine, "PLATFORM_PASSWORD_HASH", valeur)
        p.mot_de_passe = valeur
        with depot.connexion() as c:
            c.execute("DELETE FROM sessions")
            c.execute("DELETE FROM tickets")
        depot.auditer("securite.mot_de_passe_modifie", None, acteur)
        return {"message": "Mot de passe enregistré. Reconnectez-vous."}

    @app.get("/api/vue-ensemble")
    async def vue(request: Request):
        auth.acteur(request)
        return {
            **depot.statistiques(),
            "sante": await services.sante(),
            "runbooks": len(corpus.lister()),
            "journal": depot.journal(8),
            "version": __version__,
        }

    @app.get("/api/analyses")
    async def analyses(
        request: Request,
        page: int = Query(1, ge=1, le=10000),
        taille: int = Query(25, ge=1, le=100),
        statut: str = Query("", max_length=40),
        recherche: str = Query("", max_length=100),
    ):
        auth.acteur(request)
        return depot.lister(page=page, taille=taille, statut=statut, recherche=recherche)

    @app.post("/api/analyses", status_code=202)
    async def creer(request: Request, charge: NouvelleAnalyse):
        return moteur.creer(charge.titre, charge.alerte, auth.acteur(request, mutation=True))

    @app.get("/api/analyses/{identifiant}")
    async def analyse(request: Request, identifiant: str):
        auth.acteur(request)
        return depot.obtenir(identifiant)

    @app.post("/api/analyses/{identifiant}/decision", status_code=202)
    async def decider(request: Request, identifiant: str, charge: Decision):
        return moteur.decider(identifiant, charge.approuver, auth.acteur(request, mutation=True))

    @app.post("/api/analyses/{identifiant}/annuler")
    async def annuler(request: Request, identifiant: str):
        return await moteur.annuler(identifiant, auth.acteur(request, mutation=True))

    @app.delete("/api/analyses/{identifiant}")
    async def supprimer(request: Request, identifiant: str):
        acteur = auth.acteur(request, mutation=True)
        depot.supprimer(identifiant, acteur)
        # IDs come from an existing server-generated database record.
        dossier = moteur.racine / identifiant
        if dossier.exists() and not dossier.is_symlink() and dossier.parent == moteur.racine:
            shutil.rmtree(dossier)
        return {"supprime": True}

    @app.get("/api/analyses/{identifiant}/export")
    async def exporter(request: Request, identifiant: str, format: Literal["json", "md"] = "json"):
        acteur = auth.acteur(request)
        resultat = depot.obtenir(identifiant)
        depot.auditer("analyse.exportee", identifiant, acteur)
        if format == "json":
            texte = json.dumps(resultat, ensure_ascii=False, indent=2)
        else:
            rapport = resultat["rapport"] or {}
            diagnostic = rapport.get("diagnostic") or {}
            texte = f"# {resultat['titre']}\n\nÉtat : {resultat['statut']}\n\n{diagnostic.get('cause_probable', rapport.get('message', ''))}\n\n"
            texte += "\n".join(f"- {a}" for a in diagnostic.get("actions_proposees", []))
            texte += f"\n\nSource : {diagnostic.get('runbook_source') or 'Aucune'}\n"
        return Response(
            texte,
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="analyse-{identifiant}.{format}"'
            },
        )

    @app.get("/api/analyses/{identifiant}/evenements")
    async def evenements(request: Request, identifiant: str):
        nonlocal flux_actifs
        auth.acteur(request)
        depot.obtenir(identifiant)
        if flux_actifs >= 8:
            raise HTTPException(429, "Trop de connexions en direct.")
        flux_actifs += 1

        async def produire():
            nonlocal flux_actifs
            version = -1
            try:
                for _ in range(3600):
                    if await request.is_disconnected():
                        break
                    try:
                        auth.acteur(request)
                        resultat = depot.obtenir(identifiant)
                    except HTTPException, Introuvable:
                        break
                    if resultat["version"] != version:
                        yield "data: " + json.dumps(resultat, ensure_ascii=False) + "\n\n"
                        version = resultat["version"]
                    else:
                        yield ": maintien\n\n"
                    if resultat["statut"] not in ACTIFS:
                        break
                    await asyncio.sleep(1)
            finally:
                flux_actifs -= 1

        return StreamingResponse(
            produire(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
        )

    @app.get("/api/runbooks")
    async def runbooks(request: Request, recherche: str = Query("", max_length=200)):
        auth.acteur(request)
        return corpus.lister(recherche)

    @app.get("/api/runbooks/{nom}")
    async def runbook(request: Request, nom: str):
        auth.acteur(request)
        return corpus.lire(nom)

    @app.put("/api/runbooks/{nom}")
    async def enregistrer(request: Request, nom: str, charge: Edition):
        return corpus.ecrire(
            nom, charge.contenu, charge.empreinte, auth.acteur(request, mutation=True)
        )

    @app.get("/api/recherche")
    async def recherche(
        request: Request,
        q: str = Query(min_length=2, max_length=500),
        mode: Literal["texte", "semantique"] = "texte",
    ):
        auth.acteur(request)
        if mode == "texte":
            return {"elements": corpus.lister(q), "mode": mode}
        auth.limiter("recherche", maximum=10)
        try:
            return {"elements": await services.semantique(q), "mode": mode}
        except Exception:  # noqa: BLE001 - do not expose confidential provider errors.
            raise HTTPException(
                503, "Recherche sémantique indisponible. Vérifier l'index et l'inférence locale."
            ) from None

    @app.get("/api/sante")
    async def sante(request: Request):
        auth.acteur(request)
        return await services.sante()

    @app.get("/api/preparation")
    async def preparer(request: Request):
        auth.acteur(request)
        return await preparation.verifier()

    @app.get("/api/journal")
    async def journal(request: Request, limite: int = Query(20, ge=1, le=100)):
        auth.acteur(request)
        return {"elements": depot.journal(limite)}

    @app.get("/api/observabilite")
    async def observabilite(request: Request):
        auth.acteur(request)
        return {"cibles": await services.cibles(), "journal": depot.journal()}

    @app.post("/api/operations/{operation}", status_code=202)
    async def operation(request: Request, operation: str):
        acteur = auth.acteur(request, mutation=True)
        if operation not in OPERATIONS:
            raise HTTPException(404, "Opération inconnue.")
        return moteur.creer(operation, "", acteur, operation)

    @app.get("/api/parametres")
    async def parametres(request: Request):
        auth.acteur(request)
        return {
            "version": __version__,
            "acces": "Local privé",
            "alias": "local",
            "file_max": p.taille_file,
            "retention_jours": p.retention_jours,
            "duree_session_heures": p.duree_session / 3600,
            "mot_de_passe": bool(p.mot_de_passe),
        }

    @app.get("/api/outils")
    async def outils(request: Request):
        auth.acteur(request)
        return {"outils": OUTILS}

    @app.get("/api/voix/statut")
    async def voix_statut(request: Request, langue: Literal["en", "fr"] = "en"):
        auth.acteur(request)
        return await voix.statut(langue)

    @app.post("/api/voix/parler")
    async def parler(request: Request, charge: Parole):
        auth.acteur(request, mutation=True)
        auth.limiter("synthese", maximum=20)
        return Response(await voix.parler(charge.texte, charge.langue), media_type="audio/wav")

    @app.post("/api/voix/transcrire")
    async def transcrire(request: Request, charge: Audio):
        auth.acteur(request, mutation=True)
        auth.limiter("transcription", maximum=12)
        return await voix.transcrire(charge.audio, charge.langue)

    @app.post("/api/assistant/dialogue")
    async def dialogue(request: Request, charge: Dialogue):
        auth.acteur(request, mutation=True)
        auth.limiter("dialogue", maximum=8)
        if charge.messages[-1].role != "user":
            raise HTTPException(422, "Le dernier message doit être celui de l'opérateur.")
        if moteur.inference.locked() or not moteur.file.empty():
            raise HTTPException(
                409, "Le moteur local traite une analyse. Réessayer lorsqu'elle sera terminée."
            )
        async with moteur.inference:
            return await dialoguer(p, [m.model_dump() for m in charge.messages], charge.langue)

    @app.get("/{chemin:path}")
    async def console(chemin: str):
        if chemin.startswith("api/"):
            raise HTTPException(404, "Route inconnue.")
        candidat = (p.web / chemin).resolve()
        if candidat.is_relative_to(p.web.resolve()) and candidat.is_file():
            return FileResponse(candidat)
        if (p.web / "index.html").is_file():
            return FileResponse(p.web / "index.html", headers={"Cache-Control": "no-cache"})
        return JSONResponse(
            {"message": "Construire la console avec npm ci puis npm run build dans apps/console."},
            status_code=503,
        )

    return app
