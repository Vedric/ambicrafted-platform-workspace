"""Opaque sessions, one-use tickets and explicit browser request boundaries."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse

from .config import Parametres
from .depot import Depot

COOKIE = "ambicrafted_session"


def empreinte(valeur: str) -> str:
    return hashlib.sha256(valeur.encode()).hexdigest()


def hacher_mot_de_passe(valeur: str) -> str:
    if not 14 <= len(valeur) <= 128:
        raise ValueError("Le mot de passe doit contenir entre 14 et 128 caractères.")
    sel = secrets.token_bytes(16)
    resultat = hashlib.scrypt(valeur.encode(), salt=sel, n=32768, r=8, p=1, maxmem=64 * 1024 * 1024)
    return sel.hex() + "$" + resultat.hex()


def verifier_mot_de_passe(valeur: str, attendu: str) -> bool:
    try:
        if len(valeur) > 128:
            return False
        sel, resultat = attendu.split("$")
        calcule = hashlib.scrypt(
            valeur.encode(), salt=bytes.fromhex(sel), n=32768, r=8, p=1, maxmem=64 * 1024 * 1024
        )
        return hmac.compare_digest(calcule.hex(), resultat)
    except ValueError:
        return False


class Authentification:
    def __init__(self, parametres: Parametres, depot: Depot):
        self.p = parametres
        self.d = depot
        self.essais: dict[str, deque] = defaultdict(deque)

    def csrf(self, identifiant: str) -> str:
        return hmac.new(self.p.cle.encode(), identifiant.encode(), "sha256").hexdigest()

    def limiter(self, groupe: str, maximum=5, intervalle=60) -> None:
        essais = self.essais[groupe]
        instant = time.monotonic()
        while essais and essais[0] < instant - intervalle:
            essais.popleft()
        if len(essais) >= maximum:
            raise HTTPException(
                429, "Trop de tentatives. Réessayer dans une minute.", headers={"Retry-After": "60"}
            )
        essais.append(instant)

    def ticket(self) -> str:
        self.limiter("ticket", 20)
        jeton = secrets.token_urlsafe(32)
        with self.d.connexion() as c:
            c.execute("DELETE FROM tickets WHERE expire<?", (time.time(),))
            c.execute("INSERT INTO tickets VALUES(?,?)", (empreinte(jeton), time.time() + 60))
        return jeton

    def echanger(self, jeton: str) -> str:
        self.limiter("echange", 30)
        with self.d.connexion() as c:
            c.execute("BEGIN IMMEDIATE")
            ligne = c.execute(
                "DELETE FROM tickets WHERE empreinte=? AND expire>? RETURNING empreinte",
                (empreinte(jeton), time.time()),
            ).fetchone()
            if not ligne:
                raise HTTPException(401, "Lien de connexion expiré ou déjà utilisé.")
        return self.creer_session()

    def creer_session(self) -> str:
        jeton = secrets.token_urlsafe(32)
        with self.d.connexion() as c:
            c.execute("DELETE FROM sessions WHERE expire<?", (time.time(),))
            c.execute(
                "INSERT INTO sessions VALUES(?,?)",
                (empreinte(jeton), time.time() + self.p.duree_session),
            )
        self.d.auditer("session.ouverte", None, "operateur")
        return jeton

    def session(self, jeton: str) -> str | None:
        if not jeton or len(jeton) > 128:
            return None
        identifiant = empreinte(jeton)
        with self.d.connexion() as c:
            ligne = c.execute(
                "SELECT 1 FROM sessions WHERE empreinte=? AND expire>?", (identifiant, time.time())
            ).fetchone()
        return identifiant if ligne else None

    def acteur(self, requete: Request, *, mutation: bool = False) -> str:
        autorisation = requete.headers.get("authorization", "")
        if autorisation:
            if hmac.compare_digest(autorisation.encode(), ("Bearer " + self.p.cle).encode()):
                return "cli"
            raise HTTPException(401, "Authentification requise.")
        session = self.session(requete.cookies.get(COOKIE, ""))
        if not session:
            raise HTTPException(401, "Session expirée. Reconnectez-vous.")
        if mutation:
            self.verifier_origine(requete)
            if not hmac.compare_digest(
                requete.headers.get("x-csrf-token", "").encode(), self.csrf(session).encode()
            ):
                raise HTTPException(403, "Validation de la session requise. Actualiser la page.")
        return "operateur"

    def verifier_origine(self, requete: Request) -> None:
        if requete.headers.get("origin") not in self.p.origines:
            raise HTTPException(403, "Origine de la requête refusée.")


class FrontiereHTTP:
    """Bound request bodies before parsing and protect every response."""

    def __init__(self, app, parametres: Parametres):
        self.app, self.p = app, parametres

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        entetes = dict(scope.get("headers", []))
        hotes = {urlsplit(o).netloc.encode() for o in self.p.origines}

        async def envoyer(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"cross-origin-opener-policy", b"same-origin"),
                        (b"cross-origin-resource-policy", b"same-origin"),
                        (
                            b"permissions-policy",
                            b"camera=(), microphone=(self), speaker-selection=(self), geolocation=()",
                        ),
                        (
                            b"content-security-policy",
                            b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; media-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
                        ),
                    ]
                )
                if scope["path"].startswith("/api/"):
                    message["headers"].append((b"cache-control", b"no-store"))
            await send(message)

        async def refuser(code, detail):
            await JSONResponse({"detail": detail}, status_code=code)(scope, receive, envoyer)

        if entetes.get(b"host") not in hotes:
            return await refuser(400, "Hôte refusé.")
        origine = entetes.get(b"origin")
        if origine and origine.decode(errors="replace") not in self.p.origines:
            return await refuser(403, "Origine refusée.")
        if entetes.get(b"sec-fetch-site") == b"cross-site":
            return await refuser(403, "Accès intersite refusé.")
        try:
            longueur = int(entetes.get(b"content-length", b"0"))
        except ValueError:
            return await refuser(400, "Longueur invalide.")
        document = scope["path"].startswith("/api/conversations/") and scope["path"].endswith("/pieces")
        maximum = 11_300_000 if scope["path"] == "/api/voix/transcrire" or document else 96_000
        if longueur > maximum or longueur < 0:
            return await refuser(413, "Requête trop volumineuse.")
        if scope["method"] in {"POST", "PUT", "PATCH", "DELETE"}:
            if entetes.get(b"content-type", b"").split(b";")[0] != b"application/json":
                return await refuser(415, "Une requête JSON est requise.")
            corps = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                corps.extend(message.get("body", b""))
                if len(corps) > maximum:
                    return await refuser(413, "Requête trop volumineuse.")
                if not message.get("more_body"):
                    break
            livre = False
            original = receive

            async def recevoir():
                nonlocal livre
                if not livre:
                    livre = True
                    return {"type": "http.request", "body": bytes(corps), "more_body": False}
                return await original()

            receive = recevoir
        return await self.app(scope, receive, envoyer)
