"""Authentication, browser boundaries and request-validation regressions."""

import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException

from plateforme.securite import COOKIE, empreinte, hacher_mot_de_passe, verifier_mot_de_passe


@pytest.mark.parametrize(
    "chemin",
    [
        "/api/analyses",
        "/api/parametres",
        "/api/sante",
        "/api/runbooks",
        "/api/runbooks/postgres.md",
        "/api/observabilite",
        "/api/vue-ensemble",
        "/api/recherche?q=postgres",
        "/api/analyses/inexistant",
    ],
)
def test_lecture_privee_exige_authentification(client, chemin):
    assert client.get(chemin).status_code == 401


@pytest.mark.parametrize("chemin,statut", [("/api/ping", 200), ("/api/inconnue", 404)])
def test_entetes_de_securite_y_compris_erreurs(client, chemin, statut):
    reponse = client.get(chemin)
    assert reponse.status_code == statut
    assert reponse.headers["cache-control"] == "no-store"
    assert reponse.headers["x-content-type-options"] == "nosniff"
    assert reponse.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in reponse.headers["content-security-policy"]
    assert "connect-src 'self'" in reponse.headers["content-security-policy"]


def test_ticket_usage_unique_et_session_stockes_haches(client, application, parametres, bearer):
    ticket = client.post("/api/auth/ticket", headers=bearer, json={}).json()["ticket"]
    with application.state.depot.connexion() as c:
        assert c.execute("SELECT empreinte FROM tickets").fetchone()[0] == empreinte(ticket)
    reponse = client.post(
        "/api/auth/connexion", json={"ticket": ticket}, headers={"Origin": parametres.url}
    )
    assert reponse.status_code == 200
    cookie = reponse.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie
    jeton = client.cookies[COOKIE]
    with application.state.depot.connexion() as c:
        assert c.execute("SELECT empreinte FROM sessions").fetchone()[0] == empreinte(jeton)
        assert c.execute("SELECT count(*) FROM tickets").fetchone()[0] == 0
    assert client.get("/api/auth").json()["connecte"] is True
    assert (
        client.post(
            "/api/auth/connexion", json={"ticket": ticket}, headers={"Origin": parametres.url}
        ).status_code
        == 401
    )


def test_ticket_reserve_au_cli(client, session):
    assert client.post("/api/auth/ticket", headers=session, json={}).status_code == 403


def test_echange_ticket_concurrent_un_seul_gagnant(application):
    auth = application.state.auth
    ticket = auth.ticket()

    def echanger(_):
        try:
            auth.echanger(ticket)
            return 200
        except HTTPException as erreur:
            return erreur.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(echanger, range(2))) == [200, 401]


def test_ticket_expire_refuse(application):
    auth = application.state.auth
    ticket = auth.ticket()
    with application.state.depot.connexion() as c:
        c.execute("UPDATE tickets SET expire=?", (time.time() - 1,))
    with pytest.raises(HTTPException) as erreur:
        auth.echanger(ticket)
    assert erreur.value.status_code == 401


def test_session_expiree_refuse(client, application, session):
    with application.state.depot.connexion() as c:
        c.execute("UPDATE sessions SET expire=?", (time.time() - 1,))
    assert client.get("/api/analyses").status_code == 401
    assert client.get("/api/auth").json() == {
        "connecte": False,
        "mot_de_passe": False,
        "csrf": None,
    }


@pytest.mark.parametrize(
    "entetes",
    [
        {},
        {"Origin": "http://127.0.0.1:8787"},
        {"X-CSRF-Token": "incorrect"},
        {"Origin": "http://127.0.0.1:8787", "X-CSRF-Token": "incorrect"},
    ],
)
def test_mutation_session_exige_origine_et_csrf(client, session, entetes):
    assert (
        client.post(
            "/api/analyses", json={"titre": "Test", "alerte": "Alerte synthétique"}, headers=entetes
        ).status_code
        == 403
    )


def test_bearer_cli_autorise_sans_csrf_ni_origine(client, bearer):
    assert (
        client.post(
            "/api/analyses", json={"titre": "Test", "alerte": "Synthétique"}, headers=bearer
        ).status_code
        == 202
    )


def test_autorisation_incorrecte_ne_retombe_pas_sur_cookie(client, session):
    assert (
        client.get("/api/analyses", headers={"Authorization": "Bearer incorrect"}).status_code
        == 401
    )


@pytest.mark.parametrize(
    "entetes,code",
    [
        ({"Host": "attacker.example:8787"}, 400),
        ({"Origin": "https://attacker.example"}, 403),
        ({"Sec-Fetch-Site": "cross-site"}, 403),
        ({"Host": "127.0.0.1:9999"}, 400),
    ],
)
def test_frontiere_refuse_rebinding_et_intersite(client, bearer, entetes, code):
    assert client.get("/api/analyses", headers={**bearer, **entetes}).status_code == code


def test_connexion_exige_origine_meme_avec_ticket_valide(client, bearer):
    ticket = client.post("/api/auth/ticket", headers=bearer, json={}).json()["ticket"]
    assert client.post("/api/auth/connexion", json={"ticket": ticket}).status_code == 403


def test_deconnexion_invalide_session(client, session):
    assert client.post("/api/auth/deconnexion", headers=session, json={}).status_code == 200
    assert client.get("/api/analyses").status_code == 401


def test_tentatives_connexion_limitees(client, parametres):
    for _ in range(5):
        assert (
            client.post(
                "/api/auth/connexion",
                json={"mot_de_passe": "invalide"},
                headers={"Origin": parametres.url},
            ).status_code
            == 401
        )
    reponse = client.post("/api/auth/connexion", json={}, headers={"Origin": parametres.url})
    assert reponse.status_code == 429 and reponse.headers["retry-after"] == "60"


def test_mot_de_passe_sale_et_validation_stricte():
    valeur = "Phrase de test confidentielle"
    premier, second = hacher_mot_de_passe(valeur), hacher_mot_de_passe(valeur)
    assert premier != second
    assert verifier_mot_de_passe(valeur, premier)
    assert not verifier_mot_de_passe("Autre phrase de test", premier)
    assert not verifier_mot_de_passe("x" * 129, premier)
    assert not verifier_mot_de_passe(valeur, "hash incorrect")
    with pytest.raises(ValueError):
        hacher_mot_de_passe("trop court")


def test_changer_mot_de_passe_revoque_toutes_sessions_et_tickets(
    client, session, application, parametres, bearer
):
    ticket = client.post("/api/auth/ticket", headers=bearer, json={}).json()["ticket"]
    valeur = "Phrase de test locale unique"
    assert (
        client.put("/api/auth/mot-de-passe", json={"valeur": valeur}, headers=session).status_code
        == 200
    )
    assert client.get("/api/analyses").status_code == 401
    assert (
        client.post(
            "/api/auth/connexion", json={"ticket": ticket}, headers={"Origin": parametres.url}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/connexion", json={"mot_de_passe": valeur}, headers={"Origin": parametres.url}
        ).status_code
        == 200
    )
    assert (parametres.racine / ".env").stat().st_mode & 0o077 == 0
    assert application.state.depot.journal()[1]["action"] == "securite.mot_de_passe_modifie"


@pytest.mark.parametrize("valeur", ["true", "false", 1, 0, None, [], {}])
def test_decision_refuse_coercition_boolean(client, bearer, valeur):
    assert (
        client.post(
            "/api/analyses/inexistant/decision", json={"approuver": valeur}, headers=bearer
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "charge",
    [
        {"titre": "Test", "alerte": "Synthétique", "commande": "arbitraire"},
        {"titre": " ", "alerte": "Synthétique"},
        {"titre": "Test", "alerte": " "},
        {"titre": "x" * 101, "alerte": "Synthétique"},
        {"titre": "Test", "alerte": "x" * 20001},
    ],
)
def test_creation_exige_charge_bornee_sans_champs_extra(client, bearer, charge):
    assert client.post("/api/analyses", json=charge, headers=bearer).status_code == 422


def test_decision_refuse_champ_extra(client, bearer):
    assert (
        client.post(
            "/api/analyses/inexistant/decision",
            json={"approuver": True, "runbook": "injecte.md"},
            headers=bearer,
        ).status_code
        == 422
    )


@pytest.mark.parametrize("longueur,code", [("invalide", 400), ("-1", 413), ("96001", 413)])
def test_longueur_http_invalide(client, longueur, code):
    assert (
        client.post(
            "/api/auth/connexion",
            content="{}",
            headers={"Content-Type": "application/json", "Content-Length": longueur},
        ).status_code
        == code
    )


def test_corps_json_trop_grand_meme_sans_content_length(client, bearer):
    morceaux = iter([b'{"titre":"', b"x" * 96_000, b'","alerte":"test"}'])
    assert (
        client.post(
            "/api/analyses",
            content=morceaux,
            headers={**bearer, "Content-Type": "application/json"},
        ).status_code
        == 413
    )


def test_mutation_refuse_formulaire(client, bearer):
    assert client.post("/api/analyses", data={"titre": "Test"}, headers=bearer).status_code == 415


def test_validation_ne_reflete_pas_alerte_confidentielle(client, bearer):
    marqueur = "CONTENU_SYNTHETIQUE_NE_DEVANT_PAS_ETRE_REFLETE"
    reponse = client.post(
        "/api/analyses",
        json={"titre": "Test", "alerte": marqueur, "extra": marqueur},
        headers=bearer,
    )
    assert reponse.status_code == 422
    # Errors may identify the invalid field, but should not echo confidential payloads.
    assert marqueur not in json.dumps(reponse.json())


def test_authorization_non_ascii_refuse_sans_erreur_serveur(client):
    reponse = client.get("/api/analyses", headers={"Authorization": b"Bearer \xff"})
    assert reponse.status_code == 401


def test_csrf_non_ascii_refuse_sans_erreur_serveur(client, session):
    reponse = client.post(
        "/api/analyses",
        json={"titre": "Test", "alerte": "Synthétique"},
        headers={"Origin": session["Origin"], "X-CSRF-Token": b"\xff"},
    )
    assert reponse.status_code == 403
