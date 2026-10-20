"""Actual MCP gateway transport with isolated child processes and no service access."""

import asyncio
import json
import os
import shutil
import signal
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters, stdio_client

from plateforme.passerelle import Backend, ConfigurationBackend, Passerelle, configurations


@pytest.fixture
def lanceur(tmp_path):
    backend = tmp_path / "backend.py"
    backend.write_text("""import asyncio, json, os
from pathlib import Path
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
root = Path(os.environ["FIXTURE_ROOT"])
kind = os.environ["FIXTURE_BACKEND"]
(root / (kind + ".pid")).write_text(str(os.getpid()))
mcp = MCPServer(kind)
read = ToolAnnotations(read_only_hint=True, destructive_hint=False,
                       idempotent_hint=True, open_world_hint=False)
@mcp.tool(annotations=read, title="Catalogue vérifié")
def list_runbooks() -> dict[str, str]:
    return {"backend": kind, "value": "fixture.md"}
@mcp.tool(annotations=read)
async def read_runbook(nom: str) -> str:
    if nom == "slow.md":
        try:
            await asyncio.sleep(30)
        finally:
            (root / "cancelled").touch()
    if nom == "error.md":
        raise ValueError("PRIVATE_SYNTHETIC_ERROR")
    if nom == "big.md":
        return "X" * 1_000_001
    return "# Fixture\\n\\nVérifier le service."
@mcp.tool(annotations=read)
def plateforme_sante() -> dict[str, str]:
    return {"backend": kind}
@mcp.tool()
def approuver() -> str:
    (root / "FORBIDDEN").touch()
    return "never"
mcp.run()
""")

    @asynccontextmanager
    async def ouvrir(*, delai=2.0, panne=False):
        entree = tmp_path / "gateway.py"
        entree.write_text(f"""import asyncio, logging, os
from pathlib import Path
from mcp import StdioServerParameters
from plateforme import passerelle as p
Path({str(tmp_path / "gateway.pid")!r}).write_text(str(os.getpid()))
logging.disable(logging.CRITICAL)
p.DELAI_APPEL = {delai!r}
definitions = []
for name in ["runbooks", "controle"]:
    args = [{str(backend)!r}] if name != "runbooks" or not {panne!r} else ["-c", "raise SystemExit(1)"]
    definitions.append(p.ConfigurationBackend(name, StdioServerParameters(
        command={sys.executable!r}, args=args,
        env={{"FIXTURE_ROOT": {str(tmp_path)!r}, "FIXTURE_BACKEND": name}})))
asyncio.run(p.Passerelle(definitions).executer())
""")
        with (tmp_path / "gateway.stderr").open("w") as journal:
            async with asyncio.timeout(20):
                async with (
                    stdio_client(
                        StdioServerParameters(
                            command=sys.executable,
                            args=[str(entree)],
                            env={"HOME": str(tmp_path)},
                        ),
                        errlog=journal,
                    ) as (lecture, ecriture),
                    ClientSession(lecture, ecriture) as session,
                ):
                    await session.initialize()
                    yield session
        assert "PRIVATE_SYNTHETIC_ERROR" not in (tmp_path / "gateway.stderr").read_text()
        assert not (tmp_path / "FORBIDDEN").exists()
        for pid in tmp_path.glob("*.pid"):
            with pytest.raises(ProcessLookupError):
                os.kill(int(pid.read_text()), 0)

    return ouvrir


@pytest.mark.asyncio
async def test_stdio_reel_namespaces_schemas_annotations_resultat_structure(lanceur):
    async with lanceur() as session:
        outils = {o.name: o for o in (await session.list_tools()).tools}
        assert set(outils) == {
            "runbooks__list_runbooks",
            "runbooks__read_runbook",
            "controle__plateforme_sante",
        }
        outil = outils["runbooks__list_runbooks"]
        assert outil.title == "Catalogue vérifié"
        assert outil.output_schema is not None
        assert outil.annotations.read_only_hint and not outil.annotations.destructive_hint
        assert outils["runbooks__read_runbook"].input_schema["required"] == ["nom"]
        reponse = await session.call_tool("runbooks__list_runbooks", {})
        assert not reponse.is_error
        assert reponse.structured_content == {"backend": "runbooks", "value": "fixture.md"}
        controle = await session.call_tool("controle__plateforme_sante", {})
        assert controle.structured_content == {"backend": "controle"}


@pytest.mark.asyncio
async def test_refus_sans_dispatch_erreurs_et_resultats_bornes(lanceur):
    async with lanceur() as session:
        for nom, arguments in [
            ("approuver", {}),
            ("runbooks__approuver", {}),
            ("controle__list_runbooks", {}),
            ("list_runbooks", {}),
            ("runbooks__read_runbook", {"nom": "error.md"}),
            ("runbooks__read_runbook", {"nom": "big.md"}),
            ("runbooks__read_runbook", {"nom": "x" * 20_000}),
            ("runbooks__read_runbook", {"nom": ["invalid"]}),
        ]:
            resultat = await session.call_tool(nom, arguments)
            assert resultat.is_error
            assert len(resultat.model_dump_json()) < 1_000
            assert "PRIVATE_SYNTHETIC_ERROR" not in resultat.model_dump_json()


@pytest.mark.asyncio
async def test_backend_indisponible_isole_et_autre_backend_utilisable(lanceur):
    async with lanceur(panne=True) as session:
        assert [o.name for o in (await session.list_tools()).tools] == [
            "controle__plateforme_sante"
        ]
        assert (await session.call_tool("runbooks__list_runbooks", {})).is_error
        assert not (await session.call_tool("controle__plateforme_sante", {})).is_error


@pytest.mark.asyncio
async def test_timeout_arrete_enfant_sans_bloquer_autre_backend(lanceur, tmp_path):
    async with lanceur(delai=0.08) as session:
        resultat = await session.call_tool("runbooks__read_runbook", {"nom": "slow.md"})
        assert resultat.is_error
        assert not (await session.call_tool("controle__plateforme_sante", {})).is_error
    assert (tmp_path / "cancelled").exists()


@pytest.mark.asyncio
async def test_appel_concurrent_borne_et_annulation_propagee(lanceur, tmp_path):
    async with lanceur() as session:
        lente = asyncio.create_task(session.call_tool("runbooks__read_runbook", {"nom": "slow.md"}))
        await asyncio.sleep(0.1)
        occupe = await session.call_tool("runbooks__list_runbooks", {})
        assert occupe.is_error and "occupé" in occupe.content[0].text
        assert not (await session.call_tool("controle__plateforme_sante", {})).is_error
        lente.cancel()
        with pytest.raises(asyncio.CancelledError):
            await lente
        for _ in range(40):
            if (tmp_path / "cancelled").exists():
                break
            await asyncio.sleep(0.02)
        assert (tmp_path / "cancelled").exists()
        assert not (await session.call_tool("runbooks__list_runbooks", {})).is_error


@pytest.mark.asyncio
@pytest.mark.parametrize("idle", [0, 0.25])
async def test_sigterm_ferme_aussi_les_deux_sous_processus(lanceur, tmp_path, idle):
    async with lanceur():
        # An already-idle client keeps stdin open while the signal is handled.
        # Signalling immediately after initialize can miss the blocked-read race.
        await asyncio.sleep(idle)
        os.kill(int((tmp_path / "gateway.pid").read_text()), signal.SIGTERM)
        # Observe signal-driven shutdown while the client's transport stays open.
        # A fixed sleep races its teardown/kill deadline against the gateway's
        # own child cleanup on slower runners and tests two shutdowns at once.
        limite = asyncio.get_running_loop().time() + 10
        while True:
            vivants = []
            for fichier in tmp_path.glob("*.pid"):
                try:
                    os.kill(int(fichier.read_text()), 0)
                except ProcessLookupError:
                    continue
                vivants.append(fichier.stem)
            if not vivants:
                break
            assert asyncio.get_running_loop().time() < limite, f"MCP survivors: {vivants}"
            await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_entree_production_deux_backends_reels_et_api_authentifiee(
    parametres, serveur_http, tmp_path
):
    source = Path(__file__).resolve().parents[3] / "mcp-servers/runbooks"
    destination = parametres.racine / "mcp-servers/runbooks"
    (destination / ".venv/bin").mkdir(parents=True)
    lanceur = destination / ".venv/bin/python"
    lanceur.write_text(
        f"#!{sys.executable}\nimport os, sys\nos.execv({sys.executable!r}, "
        f"[{sys.executable!r}, *sys.argv[1:]])\n"
    )
    lanceur.chmod(0o700)
    for nom in ["server.py", "indexer.py", "fichiers.py"]:
        shutil.copyfile(source / nom, destination / nom)
    env = {
        "PLATFORM_ROOT": str(parametres.racine),
        "HOME": str(tmp_path),
        "PLATFORM_STATE_DIR": str(parametres.etat),
        "PLATFORM_PORT": str(serveur_http.base_url.port),
    }
    avant = serveur_http.get("/api/journal").json()
    with open(os.devnull, "w") as journal:  # noqa: ASYNC230 - fixed null device for protocol logs.
        async with asyncio.timeout(20):
            async with (
                stdio_client(
                    StdioServerParameters(
                        command=sys.executable,
                        args=["-m", "plateforme.passerelle"],
                        env=env,
                    ),
                    errlog=journal,
                ) as (lecture, ecriture),
                ClientSession(lecture, ecriture) as session,
            ):
                await session.initialize()
                outils = (await session.list_tools()).tools
                assert len(outils) == 15
                lecture = await session.call_tool("runbooks__read_runbook", {"nom": "postgres.md"})
                assert not lecture.is_error
                source_lue = json.loads(lecture.content[0].text)
                assert source_lue["fichier"] == "postgres.md" and source_lue["sha256"]
                controle = await session.call_tool("controle__plateforme_sante", {})
                assert not controle.is_error and json.loads(controle.content[0].text)["ok"] is True
                assert parametres.cle not in controle.model_dump_json()
    assert serveur_http.get("/api/journal").json() == avant


def test_configuration_profils_fermes_et_credentials_separes(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATFORM_ROOT", str(tmp_path))
    monkeypatch.setenv("CONFIDENTIAL_KEY", "synthetic-confidential")
    monkeypatch.setenv("PLATFORM_UI_KEY", "synthetic-control")
    monkeypatch.setenv("ORCHESTRATOR_KEY", "synthetic-not-for-local-tools")
    monkeypatch.setenv("HTTP_PROXY", "https://proxy.example.invalid")
    monkeypatch.setenv("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
    monkeypatch.setenv("QDRANT_URL", "http://127.0.0.1:6333")
    definitions = configurations()
    runbooks, controle = (d.processus for d in definitions)
    assert runbooks.env["CONFIDENTIAL_KEY"] == "synthetic-confidential"
    assert "CONFIDENTIAL_KEY" not in controle.env
    for processus in [runbooks, controle]:
        assert not {"PLATFORM_UI_KEY", "ORCHESTRATOR_KEY", "HTTP_PROXY"} & processus.env.keys()
    assert [d.nom for d in configurations("runbooks")] == ["runbooks"]
    assert [d.nom for d in configurations("controle")] == ["controle"]
    with pytest.raises(ValueError):
        configurations("arbitrary")
    monkeypatch.setenv("QDRANT_URL", "https://outside.example.invalid")
    with pytest.raises(ValueError):
        configurations("runbooks")


def test_profils_restreints_ne_lisent_pas_configuration_privee(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATFORM_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "plateforme.passerelle.lire_environnement", lambda _: pytest.fail(".env read")
    )
    configurations("runbooks")
    configurations("controle")


def test_rejet_collision_et_backend_inconnu():
    processus = StdioServerParameters(command=sys.executable)
    with pytest.raises(ValueError):
        Passerelle([ConfigurationBackend("unknown", processus)])
    with pytest.raises(ValueError):
        Passerelle([ConfigurationBackend("runbooks", processus)] * 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["duplicate", "write", "openworld", "task", "oversized", "cursor"])
async def test_inventaire_backend_ambigu_ou_capacite_elargie_refuse(mode, tmp_path):
    fichier = tmp_path / "inventory.py"
    fichier.write_text("""import asyncio, sys
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import ListToolsResult, Tool, ToolAnnotations, ToolExecution
mode = sys.argv[1]
async def inventory(ctx, params):
    tool = Tool(name="list_runbooks", input_schema={"type": "object"},
        annotations=ToolAnnotations(read_only_hint=mode != "write",
            destructive_hint=False, open_world_hint=mode == "openworld"))
    if mode == "task":
        tool.execution = ToolExecution(task_support="optional")
    if mode == "oversized":
        tool.description = "x" * 66000
    Path(__file__).with_suffix(".read").touch()
    return ListToolsResult(tools=[tool, tool] if mode == "duplicate" else [tool],
        next_cursor="more" if mode == "cursor" else None)
server = Server("fixture", on_list_tools=inventory)
async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
asyncio.run(main())
""")
    backend = Backend(
        ConfigurationBackend(
            "runbooks", StdioServerParameters(command=sys.executable, args=[str(fichier), mode])
        )
    )
    async with asyncio.timeout(10):
        await backend.servir()
    assert backend.echec and backend.pret.is_set()
    assert fichier.with_suffix(".read").is_file()
    assert backend.session is None and backend.outils == {}


@pytest.mark.asyncio
async def test_readiness_utilise_gateway_et_profils_sans_secrets(application, monkeypatch):
    preparation = application.state.preparation
    appels = []

    async def inventaire(executable, arguments, env):
        from plateforme.passerelle import AUTORISES

        assert executable == sys.executable
        assert arguments[:3] == ["-m", "plateforme.passerelle", "--profil"]
        assert "CONFIDENTIAL_KEY" not in env and "PLATFORM_UI_KEY" not in env
        profil = arguments[-1]
        appels.append(profil)
        return {profil + "__" + nom for nom in AUTORISES[profil]}

    monkeypatch.setattr("plateforme.preparation.inventorier_mcp", inventaire)
    for cible in ["runbooks", "control"]:
        resultat = (await preparation.mcp(cible))[0]
        assert resultat["status"] == "pass" and resultat["evidence"]["gateway"] == "stdio"
    assert appels == ["runbooks", "controle"]
