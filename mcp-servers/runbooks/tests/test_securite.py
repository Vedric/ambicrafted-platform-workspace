"""Trust boundaries of files, embeddings and index publication."""

import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fichiers
import indexer
import server


@pytest.fixture(autouse=True)
def corpus(tmp_path, monkeypatch):
    root = tmp_path / "runbooks"
    root.mkdir()
    (root / "normal.md").write_text("# Normal\nContenu public.\n")
    outside = tmp_path / "outside.txt"
    outside.write_text("OUTSIDE_CORPUS")
    (root / "linked.md").symlink_to(outside)
    monkeypatch.setattr(server, "RUNBOOK_DIR", root)
    monkeypatch.setattr(
        httpx.Client, "send", lambda *a, **k: pytest.fail("Réseau interdit")
    )
    return root


@pytest.mark.parametrize("operation", ["read", "list", "search", "index"])
def test_no_reader_follows_symlinks(corpus, operation):
    outputs = {
        "read": lambda: server.read_runbook("linked.md"),
        "list": server.list_runbooks,
        "search": lambda: server.search_runbooks("OUTSIDE"),
        "index": lambda: repr(indexer.collecter(corpus)),
    }
    assert "OUTSIDE_CORPUS" not in outputs[operation]()


@pytest.mark.parametrize(
    "name", ["../outside.txt", "/etc/passwd", ".env", "a/b.md", "a\\b.md"]
)
def test_path_escape_rejected(corpus, name):
    assert server.read_runbook(name).startswith("Refusé")


def test_non_regular_and_oversized_files_rejected(corpus):
    os.mkfifo(corpus / "pipe.md")
    assert server.read_runbook("pipe.md").startswith("Refusé")
    (corpus / "huge.md").write_bytes(b"a" * (fichiers.MAX_OCTETS + 1))
    assert server.read_runbook("huge.md").startswith("Refusé")


def test_symlink_is_checked_at_open_not_only_when_listed(corpus, monkeypatch):
    original = fichiers.os.open

    def swap(path, flags, *args, **kwargs):
        if path == "normal.md":
            (corpus / "normal.md").unlink()
            (corpus / "normal.md").symlink_to(corpus.parent / "outside.txt")
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(fichiers.os, "open", swap)
    assert server.read_runbook("normal.md").startswith("Refusé")


def test_reads_have_verifiable_digest(corpus):
    response = json.loads(server.read_runbook("normal.md"))
    assert response["fichier"] == "normal.md"
    assert response["sha256"] == hashlib.sha256(response["texte"].encode()).hexdigest()
    assert response["tronque"] is False


def test_catastrophic_regex_is_just_literal_text(corpus):
    (corpus / "re.md").write_text("a" * 100_000 + "!")
    assert "Aucun résultat" in server.search_runbooks("(a+)+$")


@pytest.mark.parametrize("context", [-1, 11, 100000, True])
def test_context_is_bounded(context):
    assert "refusée" in server.search_runbooks("public", context)


@pytest.mark.parametrize(
    "data",
    [
        [],
        [{"index": 1, "embedding": [0.1] * 768}],
        [{"index": 0, "embedding": [0.1]}],
        [{"index": 0, "embedding": [float("nan")] * 768}],
        [{"index": 0, "embedding": [0.0] * 768}],
    ],
)
def test_invalid_embeddings_are_rejected(monkeypatch, data):
    monkeypatch.setenv("CONFIDENTIAL_KEY", "test-placeholder")
    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda *a, **kw: (
            httpx.Response(200, json={"data": data})
            if data
            and not any(isinstance(x, float) and x != x for x in data[0]["embedding"])
            else httpx.Response(200, text=json.dumps({"data": data}))
        ),
    )
    with pytest.raises(indexer.ErreurPipeline):
        indexer.embarquer(["synthetic"], prefixe=indexer.PREFIXE_REQUETE)


class Database:
    """Model the externally visible alias; failed writes never change it."""

    def __init__(self, *, failure=None):
        self.failure = failure
        self.alias = "previous"
        self.versions = {"previous": 7}
        self.closed = False

    def get_aliases(self):
        return SimpleNamespace(
            aliases=[
                SimpleNamespace(
                    alias_name=indexer.COLLECTION, collection_name=self.alias
                )
            ]
        )

    def collection_exists(self, name):
        return name in self.versions

    def create_collection(self, name, **kw):
        self.versions[name] = 0

    def upsert(self, name, *, points, wait):
        if self.failure == "write":
            raise OSError("synthetic")
        self.versions[name] = len(points)

    def count(self, name, **kw):
        return SimpleNamespace(
            count=0 if self.failure == "count" else self.versions[name]
        )

    def update_collection_aliases(self, *, change_aliases_operations):
        if self.failure == "switch":
            raise OSError("synthetic")
        self.alias = change_aliases_operations[-1].create_alias.collection_name

    def close(self):
        self.closed = True


@pytest.mark.parametrize("failure", ["write", "count", "switch", None])
def test_index_publication_is_atomic(monkeypatch, failure):
    db = Database(failure=failure)
    monkeypatch.setattr(indexer, "QdrantClient", lambda **kw: db)
    monkeypatch.setattr(indexer, "embarquer", lambda *a, **kw: [[0.1] * 768])
    fragment = indexer.Fragment("normal.md", "# Normal", 1, "Contenu public.")
    if failure:
        with pytest.raises(indexer.ErreurPipeline):
            indexer.indexer([fragment])
        assert db.alias == "previous"
    else:
        assert indexer.indexer([fragment]) == 1
        assert db.alias != "previous"
    assert db.versions["previous"] == 7
    assert db.closed


def test_stale_index_never_supplies_old_content(corpus, monkeypatch):
    class Client:
        def __init__(self, **kw):
            pass

        def collection_exists(self, *a):
            return True

        def query_points(self, *a, **kw):
            assert kw["score_threshold"] == 0.60
            return SimpleNamespace(
                points=[
                    SimpleNamespace(
                        payload={"corpus_sha256": "obsolete", "texte": "STALE_CONTENT"},
                        score=0.9,
                    )
                ]
            )

        def close(self):
            pass

    monkeypatch.setattr(server, "QdrantClient", Client)
    monkeypatch.setattr(server, "embarquer", lambda *a, **kw: [[0.1] * 768])
    response = server.semantic_search("synthetic")
    assert "Index périmé" in response
    assert "STALE_CONTENT" not in response
