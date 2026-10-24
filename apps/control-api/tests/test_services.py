"""Probe contracts tolerate unavailable and malformed local dependencies."""

import asyncio
import base64
import secrets

import httpx
import pytest

from plateforme.config import enregistrer_secret
from plateforme.corpus import instantane_index
from plateforme.services import SERVICES, Services


def transport_simule(monkeypatch, repondre):
    vrai_client = httpx.AsyncClient
    appels = []

    def intercepter(requete):
        appels.append(requete)
        return repondre(requete)

    def client(**kwargs):
        assert kwargs["trust_env"] is False
        return vrai_client(transport=httpx.MockTransport(intercepter), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    return appels


def reponse_valide(requete):
    if requete.url.path == "/api/tags":
        return httpx.Response(200, json={"models": [{"name": "local", "size": 1024}]})
    if requete.url.path == "/collections/runbooks-current":
        return httpx.Response(200, json={"result": {"points_count": 7, "status": "green"}})
    return httpx.Response(200, json={})


@pytest.mark.asyncio
async def test_credentials_scoped_to_service_without_response_leak(parametres, monkeypatch):
    lecture, ecriture, prom = (secrets.token_urlsafe(48) for _ in range(3))
    for nom, valeur in (
        ("QDRANT_READ_ONLY_API_KEY", lecture),
        ("QDRANT_API_KEY", ecriture),
        ("PROMETHEUS_PASSWORD", prom),
    ):
        enregistrer_secret(parametres.racine, nom, valeur)
    appels = transport_simule(monkeypatch, reponse_valide)
    services = Services(parametres)
    resultat = await services.sante()
    await services.cibles()
    for appel in appels:
        if appel.url.port == 6333:
            assert appel.headers["api-key"] == lecture
            assert "authorization" not in appel.headers
        elif appel.url.port == 9090:
            assert (
                appel.headers["authorization"]
                == "Basic " + base64.b64encode(("platform:" + prom).encode()).decode()
            )
            assert "api-key" not in appel.headers
        else:
            assert "authorization" not in appel.headers and "api-key" not in appel.headers
        assert ecriture not in str(appel.headers)
    assert all(secret not in str(resultat) for secret in (lecture, ecriture, prom))
    env = parametres.environnement_agent()
    assert env["QDRANT_READ_ONLY_API_KEY"] == lecture
    assert "QDRANT_API_KEY" not in env and "PROMETHEUS_PASSWORD" not in env


@pytest.mark.asyncio
async def test_sante_sondes_fixes_cache_et_coalescence(parametres, monkeypatch):
    appels = transport_simule(monkeypatch, reponse_valide)
    services = Services(parametres)
    premier, second = await asyncio.gather(services.sante(), services.sante())
    assert premier == second
    assert premier["ok"] is True
    assert len(premier["services"]) == len(SERVICES)
    assert premier["modeles"] == [{"nom": "local", "taille": 1024}]
    assert premier["index"] == {"points": 7, "statut": "green"}
    assert len(appels) == len(SERVICES) + 2
    assert {r.url.host for r in appels} <= {"127.0.0.1", "172.17.0.1"}
    assert all("authorization" not in r.headers for r in appels)
    await services.sante()
    assert len(appels) == len(SERVICES) + 2


@pytest.mark.asyncio
async def test_un_instantane_par_rafraichissement_et_identifiants_renouveles(parametres, monkeypatch):
    premiere, seconde = (secrets.token_urlsafe(48) for _ in range(2))
    lectures = []

    def configuration(racine):
        lectures.append(racine)
        return {"QDRANT_READ_ONLY_API_KEY": premiere if len(lectures) == 1 else seconde}

    monkeypatch.setattr("plateforme.services.lire_environnement", configuration)
    appels = transport_simule(monkeypatch, reponse_valide)
    services = Services(parametres)
    await asyncio.gather(services.sante(), services.sante())
    await services.sante()
    assert lectures == [parametres.racine]
    assert all(r.headers["api-key"] == premiere for r in appels if r.url.port == 6333)
    appels.clear()
    services.date = 0
    await services.sante()
    assert lectures == [parametres.racine] * 2
    assert all(r.headers["api-key"] == seconde for r in appels if r.url.port == 6333)


@pytest.mark.asyncio
async def test_sante_dependances_indisponibles(parametres, monkeypatch):
    def indisponible(requete):
        raise httpx.ConnectError("Message interne synthétique", request=requete)

    transport_simule(monkeypatch, indisponible)
    resultat = await Services(parametres).sante()
    assert resultat["ok"] is False
    assert all(not service["ok"] for service in resultat["services"])
    assert resultat["modeles"] == [] and resultat["index"] == {}
    assert "Message interne synthétique" not in str(resultat)


@pytest.mark.asyncio
@pytest.mark.parametrize("charge", [None, [], "invalide", {"models": None}, {"models": [None]}])
async def test_sante_json_malforme_ne_casse_pas_vue_ensemble(parametres, monkeypatch, charge):
    transport_simule(monkeypatch, lambda _: httpx.Response(200, json=charge))
    resultat = await Services(parametres).sante()
    assert isinstance(resultat["services"], list)
    assert resultat["modeles"] == []
    assert isinstance(resultat["index"], dict)


@pytest.mark.asyncio
async def test_cibles_filtrees_et_liste_bornee(parametres, monkeypatch):
    cibles = [
        {
            "labels": {"job": f"service-{i}"},
            "health": "up",
            "lastScrape": "date",
            "lastScrapeDuration": 0.1,
            "lastError": "Détail non public",
        }
        for i in range(50)
    ]
    transport_simule(
        monkeypatch, lambda _: httpx.Response(200, json={"data": {"activeTargets": cibles}})
    )
    resultat = await Services(parametres).cibles()
    assert len(resultat) == 40
    assert resultat[0] == {
        "nom": "service-0",
        "sante": "up",
        "dernier_scrape": "date",
        "duree_s": 0.1,
    }
    assert "Détail non public" not in str(resultat)


@pytest.mark.asyncio
@pytest.mark.parametrize("charge", [None, [], {"data": None}, {"data": {"activeTargets": [None]}}])
async def test_cibles_json_malforme_retourne_liste_vide(parametres, monkeypatch, charge):
    transport_simule(monkeypatch, lambda _: httpx.Response(200, json=charge))
    assert await Services(parametres).cibles() == []


@pytest.mark.asyncio
async def test_recherche_uniquement_alias_et_cle_confidentiels(parametres, monkeypatch):
    from plateforme.config import enregistrer_secret

    enregistrer_secret(parametres.racine, "CONFIDENTIAL_KEY", parametres.cle)
    instantane = instantane_index(parametres.racine / "runbooks")
    source = instantane.fragments[("postgres.md", 1)]
    payload = {
        "fichier": source.fichier,
        "texte": source.texte,
        "chemin_titres": source.chemin_titres,
        "ligne_debut": source.ligne_debut,
        "corpus_sha256": instantane.empreinte,
    }

    def repondre(requete):
        import json

        charge = json.loads(requete.content)
        if requete.url.path == "/v1/embeddings":
            assert charge == {"model": "local-embed", "input": "search_query: incident synthétique"}
            assert requete.headers["authorization"] == "Bearer " + parametres.cle
            return httpx.Response(200, json={"data": [{"embedding": [0.1] * 768}]})
        assert "authorization" not in requete.headers
        assert charge == {
            "query": [0.1] * 768,
            "limit": 5,
            "with_payload": True,
            "score_threshold": 0.60,
        }
        return httpx.Response(
            200,
            json={
                "result": {
                    "points": [
                        {
                            "score": 0.7,
                            "payload": payload,
                        }
                    ]
                }
            },
        )

    appels = transport_simule(monkeypatch, repondre)
    resultat = await Services(parametres).semantique("incident synthétique")
    assert resultat == [
        {
            "score": 0.7,
            "donnees": payload,
        }
    ]
    assert len(appels) == 2 and all(r.url.host == "127.0.0.1" for r in appels)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "charge",
    [
        {"data": []},
        {"data": [{"embedding": [0.1, 0.2]}]},
        {"data": [{"embedding": [0.0] * 768}]},
        {"data": [{"embedding": [True] * 768}]},
        {"data": [{"embedding": [0.1] * 768, "index": 1}]},
    ],
)
async def test_vecteur_invalide_ne_parvient_jamais_a_qdrant(parametres, monkeypatch, charge):
    from plateforme.config import enregistrer_secret

    enregistrer_secret(parametres.racine, "CONFIDENTIAL_KEY", parametres.cle)
    appels = transport_simule(monkeypatch, lambda _: httpx.Response(200, json=charge))
    with pytest.raises(ValueError):
        await Services(parametres).semantique("incident synthétique")
    assert len(appels) == 1 and appels[0].url.path == "/v1/embeddings"


@pytest.mark.asyncio
async def test_recherche_sans_cle_confidentielle_ne_fait_aucun_appel(parametres, monkeypatch):
    appels = transport_simule(monkeypatch, reponse_valide)
    with pytest.raises(ValueError, match="confidentielle"):
        await Services(parametres).semantique("incident synthétique")
    assert appels == []


@pytest.mark.asyncio
async def test_reponses_locales_chunked_bornees_avant_decodage(parametres, monkeypatch):
    class TropGrand(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(150):
                yield b"x" * 8192

    transport_simule(monkeypatch, lambda _: httpx.Response(200, stream=TropGrand()))
    resultat = await Services(parametres).sante()
    assert resultat["modeles"] == [] and resultat["index"] == {}
    assert await Services(parametres).cibles() == []


@pytest.mark.asyncio
async def test_liste_modeles_excessive_ou_nom_invalide_refusee(parametres, monkeypatch):
    transport_simule(
        monkeypatch,
        lambda _: httpx.Response(200, json={"models": [{"name": "local", "size": 1024}] * 1001}),
    )
    assert (await Services(parametres).sante())["modeles"] == []


@pytest.mark.asyncio
async def test_reponse_recherche_ne_permet_pas_chemin_arbitraire(parametres, monkeypatch):
    from plateforme.config import enregistrer_secret

    enregistrer_secret(parametres.racine, "CONFIDENTIAL_KEY", parametres.cle)

    def repondre(requete):
        if requete.url.path == "/v1/embeddings":
            return httpx.Response(200, json={"data": [{"embedding": [0.1] * 768}]})
        return httpx.Response(
            200,
            json={
                "result": {
                    "points": [
                        {
                            "score": 0.7,
                            "payload": {"fichier": "../prive.md", "texte": "Synthétique"},
                        }
                    ]
                }
            },
        )

    transport_simule(monkeypatch, repondre)
    with pytest.raises(ValueError):
        await Services(parametres).semantique("incident synthétique")
