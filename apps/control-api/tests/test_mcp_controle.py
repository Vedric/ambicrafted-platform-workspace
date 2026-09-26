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
async def test_mcp_transport_reel_trois_outils_lecture_seule(parametres, serveur_http, journal_mcp):
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
    async with asyncio.timeout(15):
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
            }
            for outil in outils:
                assert not outil.input_schema.get("properties")
            resultats = {}
            for nom in ["plateforme_sante", "plateforme_analyses", "plateforme_runbooks"]:
                resultat = await session.call_tool(nom, {})
                assert resultat.is_error is False
                texte = "".join(c.text for c in resultat.content if c.type == "text")
                assert parametres.cle not in texte
                blocs = [json.loads(c.text) for c in resultat.content if c.type == "text"]
                resultats[nom] = blocs if nom == "plateforme_runbooks" else blocs[0]
            assert resultats["plateforme_sante"]["ok"] is True
            assert resultats["plateforme_analyses"]["total"] == 0
            assert {r["nom"] for r in resultats["plateforme_runbooks"]} == {
                "postgres.md",
                "systemd.md",
            }
            interdit = await session.call_tool("plateforme_approuver", {})
            assert interdit.is_error is True
    assert serveur_http.get("/api/analyses").json()["total"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "nom,chemin,charge",
    [
        ("plateforme_sante", "/api/sante", {"ok": True}),
        ("plateforme_analyses", "/api/analyses", {"elements": [], "total": 0}),
        ("plateforme_runbooks", "/api/runbooks", [{"nom": "postgres.md"}]),
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

    monkeypatch.setattr(module.Parametres, "charger", lambda: parametres)
    monkeypatch.setattr(httpx, "AsyncClient", client)
    assert await getattr(module, nom)() == charge
    assert len(appels) == 1


@pytest.mark.asyncio
async def test_adaptateur_mcp_masque_erreurs_http(parametres, monkeypatch):
    import httpx

    import plateforme.mcp as module

    vrai_client = httpx.AsyncClient
    monkeypatch.setattr(module.Parametres, "charger", lambda: parametres)
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
