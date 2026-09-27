"""Real stdio MCP protocol against an isolated, authenticated loopback API."""

import asyncio
import json
import os
import sys

import pytest
from mcp import ClientSession, StdioServerParameters, stdio_client


@pytest.fixture
def journal_mcp():
    with open(os.devnull, "w") as fichier:
        yield fichier


@pytest.mark.asyncio
async def test_mcp_transport_reel_neuf_outils_lecture_seule(parametres, serveur_http, journal_mcp):
    (parametres.racine / "runbooks/systemd.md").write_text("# Systemd\n\nVérifier le service.")
    parametres_stdio = StdioServerParameters(
        command=sys.executable,
        args=["-m", "plateforme.mcp"],
        env={
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(parametres.racine),
            "PLATFORM_ROOT": str(parametres.racine),
            "PLATFORM_STATE_DIR": str(parametres.etat),
            "PLATFORM_PORT": str(serveur_http.base_url.port),
        },
    )
    analyse = serveur_http.post(
        "/api/analyses", json={"titre": "Synthetic incident", "alerte": "Synthetic alert"}
    ).json()
    avant = serveur_http.get("/api/journal").json()
    async with asyncio.timeout(35):
        async with (
            stdio_client(parametres_stdio, errlog=journal_mcp) as (lecture, ecriture),
            ClientSession(lecture, ecriture) as session,
        ):
            await session.initialize()
            outils = (await session.list_tools()).tools
            assert {o.name for o in outils} == {
                "plateforme_sante",
                "plateforme_analyses",
                "plateforme_runbooks",
                "plateforme_preparation",
                "plateforme_outils",
                "plateforme_lire_runbook",
                "plateforme_recherche",
                "plateforme_analyse",
                "plateforme_journal",
            }
            for outil in outils:
                assert outil.annotations.read_only_hint is True
                assert outil.annotations.destructive_hint is False
                assert outil.annotations.open_world_hint is False
            resultats = {}
            for nom in ["plateforme_sante", "plateforme_analyses", "plateforme_runbooks"]:
                resultat = await session.call_tool(nom, {})
                assert resultat.is_error is False
                texte = "".join(c.text for c in resultat.content if c.type == "text")
                assert parametres.cle not in texte
                blocs = [json.loads(c.text) for c in resultat.content if c.type == "text"]
                resultats[nom] = blocs if nom == "plateforme_runbooks" else blocs[0]
            assert resultats["plateforme_sante"]["ok"] is True
            assert resultats["plateforme_analyses"]["total"] == 1
            assert {r["nom"] for r in resultats["plateforme_runbooks"]} == {
                "postgres.md",
                "systemd.md",
            }
            interdit = await session.call_tool("plateforme_approuver", {})
            assert interdit.is_error is True
            for nom, arguments, attendu in [
                ("plateforme_lire_runbook", {"nom": "postgres.md"}, "empreinte"),
                ("plateforme_recherche", {"requete": "Systemd"}, "elements"),
                ("plateforme_analyse", {"identifiant": analyse["id"]}, "statut"),
                ("plateforme_journal", {"limite": 1}, "elements"),
                ("plateforme_outils", {}, "outils"),
                ("plateforme_preparation", {}, "checks"),
            ]:
                resultat = await session.call_tool(nom, arguments)
                assert resultat.is_error is False
                charge = json.loads(resultat.content[0].text)
                assert attendu in charge
                assert parametres.cle not in json.dumps(charge)
                if nom == "plateforme_preparation":
                    assert charge["scope"] == "local-private" and charge["ready"] is False
                if nom == "plateforme_journal":
                    assert len(charge["elements"]) == 1
            for nom, arguments in [
                ("plateforme_journal", {"limite": 101}),
                ("plateforme_analyse", {"identifiant": "../auth/ticket"}),
                ("plateforme_recherche", {"requete": "ab", "mode": "remote"}),
            ]:
                assert (await session.call_tool(nom, arguments)).is_error is True
            resultat = await session.call_tool("plateforme_lire_runbook", {"nom": "../.env"})
            assert "erreur" in json.loads(resultat.content[0].text)
    assert serveur_http.get("/api/analyses").json()["total"] == 1
    assert serveur_http.get("/api/journal").json() == avant


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "nom,chemin,charge",
    [
        ("plateforme_sante", "/api/sante", {"ok": True}),
        ("plateforme_analyses", "/api/analyses", {"elements": [], "total": 0}),
        ("plateforme_runbooks", "/api/runbooks", [{"nom": "postgres.md"}]),
        ("plateforme_preparation", "/api/preparation", {"ready": False}),
        ("plateforme_outils", "/api/outils", {"outils": []}),
        ("plateforme_journal", "/api/journal", {"elements": []}),
    ],
)
async def test_adaptateur_mcp_lecture_authentifiee(parametres, monkeypatch, nom, chemin, charge):
    import httpx

    import plateforme.mcp as module

    vrai_client = httpx.AsyncClient
    appels = []

    def repondre(requete):
        appels.append(requete)
        assert requete.method == "GET" and requete.url.path == chemin
        assert requete.url.host == "127.0.0.1"
        assert requete.headers["authorization"] == "Bearer " + parametres.cle
        return httpx.Response(200, json=charge)

    def client(**kwargs):
        assert kwargs["trust_env"] is False
        return vrai_client(transport=httpx.MockTransport(repondre), **kwargs)

    monkeypatch.setattr(module.Parametres, "charger", lambda **_: parametres)
    monkeypatch.setattr(httpx, "AsyncClient", client)
    assert await getattr(module, nom)() == charge
    assert len(appels) == 1


@pytest.mark.asyncio
async def test_adaptateur_mcp_masque_erreurs_http(parametres, monkeypatch):
    import httpx

    import plateforme.mcp as module

    vrai_client = httpx.AsyncClient
    monkeypatch.setattr(module.Parametres, "charger", lambda **_: parametres)
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: vrai_client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(500, text="ERREUR_PRIVEE_SYNTHETIQUE")
            ),
            **kwargs,
        ),
    )
    resultat = await module.plateforme_analyses()
    assert set(resultat) == {"erreur"}
    assert "ERREUR_PRIVEE_SYNTHETIQUE" not in resultat["erreur"]


@pytest.mark.asyncio
@pytest.mark.parametrize("reponse", ["redirect", "oversized", "scalar", "invalid"])
async def test_reponses_mcp_bornees_pas_de_redirection(parametres, monkeypatch, reponse):
    import httpx

    import plateforme.mcp as module

    reel = httpx.AsyncClient
    appels = []

    def repondre(requete):
        appels.append(requete)
        if reponse == "redirect":
            return httpx.Response(302, headers={"location": "https://remote.example.invalid"})
        if reponse == "oversized":
            return httpx.Response(200, content=b"x" * 1_000_001)
        if reponse == "scalar":
            return httpx.Response(200, json="PRIVATE_SYNTHETIC_BODY")
        return httpx.Response(200, text="PRIVATE_SYNTHETIC_BODY")

    monkeypatch.setattr(module.Parametres, "charger", lambda **_: parametres)
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: reel(transport=httpx.MockTransport(repondre), **kwargs),
    )
    resultat = await module.plateforme_outils()
    assert resultat == module.ERREUR
    assert len(appels) == 1


@pytest.mark.asyncio
async def test_arguments_outils_valides_avant_acces_api(monkeypatch):
    from unittest.mock import AsyncMock

    import plateforme.mcp as module

    acces = AsyncMock()
    monkeypatch.setattr(module, "lire", acces)
    for resultat in [
        await module.plateforme_lire_runbook("../.env"),
        await module.plateforme_lire_runbook("a.md?url=http://remote.invalid"),
        await module.plateforme_analyse("../../auth/ticket"),
        await module.plateforme_recherche("  "),
        await module.plateforme_recherche("x" * 501),
        await module.plateforme_journal(True),
        await module.plateforme_journal(101),
    ]:
        assert "erreur" in resultat
    acces.assert_not_awaited()


@pytest.mark.asyncio
async def test_recherche_encode_parametres_sans_url_arbitraire(parametres, monkeypatch):
    import httpx

    import plateforme.mcp as module

    reel = httpx.AsyncClient
    requete = "error & url=https://remote.example.invalid/?key=synthetic"

    def repondre(r):
        assert r.method == "GET" and r.url.host == "127.0.0.1"
        assert r.url.path == "/api/recherche" and r.url.params["q"] == requete
        assert r.url.params["mode"] == "texte"
        assert set(r.url.params) == {"q", "mode"}
        return httpx.Response(200, json={"elements": []})

    monkeypatch.setattr(module.Parametres, "charger", lambda **_: parametres)
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: reel(transport=httpx.MockTransport(repondre), **kwargs),
    )
    assert await module.plateforme_recherche(requete) == {"elements": []}


@pytest.mark.asyncio
async def test_mcp_non_initialise_ne_cree_aucun_fichier(parametres, monkeypatch):
    import plateforme.mcp as module

    monkeypatch.setenv("PLATFORM_ROOT", str(parametres.racine))
    monkeypatch.setenv("PLATFORM_STATE_DIR", str(parametres.etat))
    assert await module.plateforme_preparation() == module.ERREUR
    assert not (parametres.racine / ".env").exists()
    assert not (parametres.racine / ".env.control.lock").exists()
    assert not parametres.etat.exists()


@pytest.mark.asyncio
async def test_mcp_ne_cree_pas_etat_avec_cle_existante(parametres, monkeypatch):
    import plateforme.mcp as module

    environnement = parametres.racine / ".env"
    environnement.write_text("PLATFORM_UI_KEY=" + parametres.cle + "\n")
    environnement.chmod(0o600)
    avant = environnement.read_bytes()
    monkeypatch.setenv("PLATFORM_ROOT", str(parametres.racine))
    monkeypatch.setenv("PLATFORM_STATE_DIR", str(parametres.etat))
    assert await module.plateforme_outils() == module.ERREUR
    assert environnement.read_bytes() == avant
    assert not (parametres.racine / ".env.control.lock").exists()
    assert not parametres.etat.exists()
