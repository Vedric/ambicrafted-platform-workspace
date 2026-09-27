"""Couverture complémentaire du serveur et de l'indexeur, hors réseau."""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

os.environ["SRE_TRACAGE"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import indexer
import server


@pytest.fixture(autouse=True)
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "RUNBOOK_DIR", tmp_path)
    monkeypatch.setattr(
        httpx.Client, "send", lambda *a, **k: pytest.fail("Réseau interdit")
    )
    monkeypatch.delenv("CONFIDENTIAL_KEY", raising=False)
    return tmp_path


def test_empty_inventory(setup):
    assert server.list_runbooks() == "Aucun runbook."


def test_missing_inventory(setup, monkeypatch):
    monkeypatch.setattr(server, "RUNBOOK_DIR", setup / "missing")
    assert "Répertoire absent" in server.list_runbooks()


def test_normal_read_and_inventory(setup):
    (setup / "a.md").write_text("# Test\ncontenu")
    assert json.loads(server.read_runbook("a.md"))["texte"] == "# Test\ncontenu"
    assert "a.md (14 car.) : Test" in server.list_runbooks()


def test_missing_file():
    assert server.read_runbook("missing.md").startswith("Introuvable")


def test_read_truncated(setup, monkeypatch):
    monkeypatch.setattr(server, "MAX_LECTURE", 10)
    (setup / "a.md").write_text("a" * 20)
    assert json.loads(server.read_runbook("a.md"))["tronque"] is True


def test_invalid_regex():
    assert "Aucun résultat" in server.search_runbooks("[")


def test_regex_context_and_limit(setup, monkeypatch):
    (setup / "a.md").write_text("before\nMATCH\nafter\nMATCH")
    monkeypatch.setattr(server, "MAX_RESULTATS", 1)
    result = server.search_runbooks("match", contexte=1)
    assert "a.md:2" in result and "before" in result and "after" in result
    assert "Limite atteinte" in result


def test_regex_no_result():
    assert "Aucun résultat" in server.search_runbooks("not-present")


@pytest.mark.parametrize("query", ["", "   ", "\n"])
def test_empty_semantic_query(query):
    assert server.semantic_search(query).startswith("Requête vide")


def test_semantic_missing_dependency(monkeypatch):
    monkeypatch.setattr(server, "_RAG_ERREUR", "synthetic missing module")
    assert "Repli immédiat" in server.semantic_search("synthetic")


def test_semantic_missing_key(monkeypatch):
    monkeypatch.setattr(server, "_RAG_ERREUR", "")
    result = server.semantic_search("synthetic")
    assert "CONFIDENTIAL_KEY absente" in result and "Repli immédiat" in result


@pytest.mark.parametrize("k,expected", [(0, 5), (-1, 5), (100, 20), (3, 3)])
def test_semantic_k_bounds(monkeypatch, k, expected):
    seen = {}

    class Client:
        def __init__(self, **kw):
            pass

        def collection_exists(self, *a):
            return True

        def query_points(self, *a, **kw):
            seen.update(kw)
            return SimpleNamespace(points=[])

    monkeypatch.setattr(server, "_RAG_ERREUR", "")
    monkeypatch.setattr(server, "embarquer", lambda *a, **kw: [[0.1] * 768])
    monkeypatch.setattr(server, "QdrantClient", Client)
    assert "Aucun fragment" in server.semantic_search("synthetic", k)
    assert seen["limit"] == expected


def test_chunking_heading_hierarchy_and_code(setup):
    path = setup / "a.md"
    path.write_text(
        "# Root\nIntroduction\n## First\n```bash\n# not heading\n```\n### Child\nDetails\n## Second\nLast"
    )
    chunks = indexer.decouper(path)
    assert len(chunks) == 4
    assert chunks[2].chemin_titres == "# Root > ## First > ### Child"
    assert chunks[3].chemin_titres == "# Root > ## Second"
    assert "# not heading" in chunks[1].contenu
    assert chunks[2].ligne_debut == 7


def test_chunk_ids_are_deterministic(setup):
    path = setup / "a.md"
    path.write_text("# Root\nContent")
    assert (
        indexer.decouper(path)[0].identifiant == indexer.decouper(path)[0].identifiant
    )


def test_empty_document_yields_no_chunks(setup):
    path = setup / "a.md"
    path.write_text("")
    assert indexer.decouper(path) == []


def test_embedding_requires_key_before_network():
    with pytest.raises(indexer.ErreurPipeline, match="CONFIDENTIAL_KEY absente"):
        indexer.embarquer(["synthetic"], prefixe=indexer.PREFIXE_REQUETE)
