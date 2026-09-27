"""Exercise the real MCP subprocess, worker thread and cancellation paths."""

import sys

import pytest

from sre_agent import config, outils
from sre_agent.budget import Budget


@pytest.fixture
def serveur_stdio(tmp_path, monkeypatch):
    serveur = tmp_path / "server.py"
    serveur.write_text(
        """import asyncio, hashlib, json
from mcp.server import MCPServer
mcp = MCPServer("fixture")
@mcp.tool(name="runbooks__list_runbooks")
def list_runbooks() -> str:
    return "fixture.md"
@mcp.tool(name="runbooks__read_runbook")
async def read_runbook(nom: str) -> str:
    if nom == "slow.md":
        await asyncio.sleep(30)
    if nom == "error.md":
        raise ValueError("SENSITIVE_FIXTURE_ERROR")
    texte = "# Fixture\\n\\nVérifier le pool."
    return json.dumps({"fichier": nom, "texte": texte, "tronque": False,
                       "sha256": hashlib.sha256(texte.encode()).hexdigest()})
@mcp.tool()
def ecrire() -> str:
    return "forbidden"
mcp.run()
"""
    )
    # Substitute only the uv launcher: dependencies are already installed in
    # the test interpreter, so this transport test never downloads packages.
    lanceur = tmp_path / "launcher"
    lanceur.write_text(
        f"#!{sys.executable}\nimport os,sys\nos.execv(sys.executable, [sys.executable, {str(serveur)!r}])\n"
    )
    lanceur.chmod(0o700)
    monkeypatch.setenv("SRE_UV_BIN", str(lanceur))
    monkeypatch.setenv("CONFIDENTIAL_KEY", "synthetic-fixture")
    monkeypatch.setattr(config, "MCP_RUNBOOKS_DIR", str(tmp_path))


def test_stdio_verifie_lecture_et_ferme_son_thread(serveur_stdio):
    client = outils.ClientRunbooks()
    budget = Budget(3, 1)
    with client:
        assert {o["function"]["name"] for o in client.outils_openai()} == {
            "list_runbooks",
            "read_runbook",
        }
        assert client.outils_ecartes == ["ecrire"]
        assert client.appeler("list_runbooks", {}) == "fixture.md"
        outils.executer_outil(client, "read_runbook", {"nom": "fixture.md"}, budget)
        assert budget.sources_lues == {"fixture.md": "# Fixture\n\nVérifier le pool."}
    assert not client._fil.is_alive()


def test_stdio_masque_erreur_du_serveur(serveur_stdio):
    client = outils.ClientRunbooks()
    with client:
        with pytest.raises(outils.ErreurOutil) as erreur:
            client.appeler("read_runbook", {"nom": "error.md"})
        assert "SENSITIVE_FIXTURE_ERROR" not in str(erreur.value)
    assert not client._fil.is_alive()


def test_stdio_annule_appel_lent_et_ferme_son_thread(serveur_stdio):
    client = outils.ClientRunbooks()
    with client:
        client.delai = 0.05
        with pytest.raises(outils.ErreurOutil):
            client.appeler("read_runbook", {"nom": "slow.md"})
    assert not client._fil.is_alive()
