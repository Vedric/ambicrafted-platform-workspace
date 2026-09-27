"""Semantic results must prove their current, stable, exact Markdown source."""

import ast
import asyncio
import hashlib
import json
import os
import re
import runpy
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from plateforme.config import enregistrer_secret
from plateforme.corpus import instantane_index
from plateforme.services import Services

# The application fixture replaces this method; route tests restore the real one.
SEMANTIQUE_REELLE = Services.semantique


@pytest.fixture
def index_synthetique(parametres, monkeypatch):
    enregistrer_secret(parametres.racine, "CONFIDENTIAL_KEY", parametres.cle)
    instantane = instantane_index(parametres.racine / "runbooks")
    source = instantane.fragments[("postgres.md", 1)]
    point = {
        "score": 0.60,
        "payload": {
            "fichier": source.fichier,
            "chemin_titres": source.chemin_titres,
            "ligne_debut": source.ligne_debut,
            "texte": source.texte,
            "corpus_sha256": instantane.empreinte,
        },
    }
    appels = []
    vrai_client = httpx.AsyncClient

    def installer(modifier=None, *, vide=False):
        def repondre(requete):
            appels.append(requete)
            if modifier:
                modifier(requete)
            if requete.url.path == "/v1/embeddings":
                return httpx.Response(200, json={"data": [{"embedding": [0.1] * 768}]})
            return httpx.Response(200, json={"result": {"points": [] if vide else [point]}})

        def client(**kwargs):
            assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
            return vrai_client(transport=httpx.MockTransport(repondre), **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", client)

    installer()
    return point, appels, installer


def indexeur_reel(monkeypatch):
    """Execute the actual pure parser/hash definitions, without the SDK imports.

    This guards cross-project format drift without adding Qdrant to control API
    dependencies or duplicating the reference algorithm inside this test.
    """
    repertoire = Path(__file__).resolve().parents[3] / "mcp-servers/runbooks"
    fichiers = runpy.run_path(str(repertoire / "fichiers.py"))
    arbre = ast.parse((repertoire / "indexer.py").read_text())
    noms = {"Fragment", "decouper", "collecter", "empreinte"}
    corps = [
        noeud
        for noeud in arbre.body
        if (isinstance(noeud, (ast.FunctionDef, ast.ClassDef)) and noeud.name in noms)
        or (
            isinstance(noeud, ast.Assign)
            and any(
                isinstance(cible, ast.Name) and cible.id in {"ENTETE", "CLOTURE"}
                for cible in noeud.targets
            )
        )
    ]
    module = ModuleType("_contrat_indexeur_runbooks")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    module.__dict__.update(
        dataclass=dataclass,
        Path=Path,
        re=re,
        hashlib=hashlib,
        json=json,
        lire=fichiers["lire"],
        noms=fichiers["noms"],
    )
    # Trusted repository parser only, never operator input.
    exec(  # noqa: S102
        compile(ast.Module(body=corps, type_ignores=[]), str(repertoire / "indexer.py"), "exec"),
        module.__dict__,
    )
    return module


def test_contrat_empreinte_et_fragments_avec_indexeur_reel(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.md").write_bytes(
        b" Preamble \r\n\r\n# First ###\r\n\r\nBody.\r\n## Empty\r\n### Child\r\n"
        b"  ```shell\r\n# Not a heading\r\n```\r\n\r\n# Next\r\nTail\r\n"
    )
    (corpus / "fran\u00e7ais espaces.md").write_text("# État\n\nété ☀️\n## Sous-titre\n\nVérifier.")
    (corpus / "mixed.md").write_text("~~~\n# Ignored\n```\n## Heading\ntext\n")
    (corpus / "invalid.md").write_bytes(b"# Invalid\n\xff\n")
    (corpus / "limit.md").write_bytes(b"x" * 200_000)
    (corpus / "oversized.md").write_bytes(b"x" * 200_001)
    (corpus / "a\\b.md").write_text("This invalid name is excluded by the indexer.")
    (corpus / ".hidden.md").write_text("Excluded.")
    (corpus / "empty.md").write_text("# Empty\n\n")
    (corpus / "directory.md").mkdir()
    (corpus / "link.md").symlink_to(corpus / "a.md")
    os.mkfifo(corpus / "pipe.md")

    reference = indexeur_reel(monkeypatch)
    fragments = reference.collecter(corpus)
    actuel = instantane_index(corpus)
    assert actuel.empreinte == reference.empreinte(fragments)
    assert [
        (f.fichier, f.chemin_titres, f.ligne_debut, f.texte) for f in actuel.fragments.values()
    ] == [(f.fichier, f.chemin_titres, f.ligne_debut, f.texte) for f in fragments]
    assert {f.fichier for f in actuel.fragments.values()} == {
        "a.md",
        "français espaces.md",
        "mixed.md",
        "invalid.md",
        "limit.md",
    }
    assert instantane_index(corpus) == actuel  # atime must not invalidate a read.


def test_instantane_refuse_racine_symbolique_et_plus_de_mille_entrees(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    lien = tmp_path / "lien"
    lien.symlink_to(corpus, target_is_directory=True)
    with pytest.raises(OSError):
        instantane_index(lien)
    for i in range(1001):
        (corpus / str(i)).touch()  # All entries count, even non-Markdown ones.
    with pytest.raises(ValueError, match="1 000"):
        instantane_index(corpus)


def test_budget_brut_reel_huit_millions_octets_meme_sans_fragments(tmp_path):
    for numero in range(40):
        (tmp_path / f"{numero:02}.md").write_bytes(b" " * 200_000)
    assert instantane_index(tmp_path).fragments == {}
    (tmp_path / "41.md").write_bytes(b" ")
    with pytest.raises(ValueError, match="provenance"):
        instantane_index(tmp_path)


def test_budget_expansion_reelle_titres_avant_allocation_excessive(tmp_path):
    texte = "# " + "x" * 3900 + "\nbody\n" + "## s\nx\n" * 500
    assert len(texte.encode()) < 8000  # Valid small input to the human editor.
    for numero in range(4):
        (tmp_path / f"{numero}.md").write_text(texte)
    assert len(instantane_index(tmp_path).fragments) == 2004
    (tmp_path / "4.md").write_text(texte)
    with pytest.raises(ValueError, match="provenance"):
        instantane_index(tmp_path)


def test_budget_nombre_fragments_reel_dix_mille(tmp_path):
    for numero in range(2):
        (tmp_path / f"{numero}.md").write_text("## s\nx\n" * 5000)
    assert len(instantane_index(tmp_path).fragments) == 10_000
    (tmp_path / "2.md").write_text("## s\nx\n")
    with pytest.raises(ValueError, match="provenance"):
        instantane_index(tmp_path)


def test_lecture_ignore_permissions_refusees_comme_indexeur(tmp_path, monkeypatch):
    (tmp_path / "public.md").write_text("# Public\n\nReadable.")
    secret = tmp_path / "unreadable.md"
    secret.write_text("# Unreadable\n\nExcluded from both parsers.")
    secret.chmod(0)
    try:
        reference = indexeur_reel(monkeypatch)
        actuel = instantane_index(tmp_path)
        assert actuel.empreinte == reference.empreinte(reference.collecter(tmp_path))
        assert {f.fichier for f in actuel.fragments.values()} == {"public.md"}
    finally:
        secret.chmod(0o600)


def test_mutation_pendant_lecture_detectee_par_descripteur(tmp_path, monkeypatch):
    source = tmp_path / "source.md"
    source.write_text("# Before\n\nText.")
    vrai_fdopen = os.fdopen

    class FichierModifie:
        def __init__(self, fd, mode):
            self.fichier = vrai_fdopen(fd, mode)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.fichier.close()

        def read(self, limite):
            contenu = self.fichier.read(limite)
            source.write_text("# After\n\nChanged during the descriptor read.")
            return contenu

    monkeypatch.setattr(os, "fdopen", FichierModifie)
    with pytest.raises(ValueError, match="changé"):
        instantane_index(tmp_path)


@pytest.mark.asyncio
async def test_recherche_fraiche_score_limite_et_zero_resultat(parametres, index_synthetique):
    point, appels, installer = index_synthetique
    assert await Services(parametres).semantique("service") == [
        {"score": point["score"], "donnees": point["payload"]}
    ]
    assert json.loads(appels[-1].content)["score_threshold"] == 0.60
    installer(vide=True)
    assert await Services(parametres).semantique("inconnu") == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "champ,valeur",
    [
        ("corpus_sha256", None),
        ("corpus_sha256", "0" * 64),
        ("corpus_sha256", "invalid"),
        ("ligne_debut", None),
        ("ligne_debut", 2),
        ("ligne_debut", True),
        ("chemin_titres", "# Different heading"),
        ("chemin_titres", ""),
        ("texte", "Invented source content"),
        ("texte", ""),
        ("fichier", "missing.md"),
        ("fichier", "../outside.md"),
    ],
)
async def test_payload_incomplet_ou_source_alteree_refuse(
    parametres, index_synthetique, champ, valeur
):
    point, _, _ = index_synthetique
    if valeur is None:
        del point["payload"][champ]
    else:
        point["payload"][champ] = valeur
    with pytest.raises(ValueError):
        await Services(parametres).semantique("service")


@pytest.mark.asyncio
@pytest.mark.parametrize("score", [0.59999, -1, True, "0.8"])
async def test_score_insuffisant_ou_type_invalide_refuse(parametres, index_synthetique, score):
    point, _, _ = index_synthetique
    point["score"] = score
    with pytest.raises(ValueError):
        await Services(parametres).semantique("service")


@pytest.mark.asyncio
@pytest.mark.parametrize("changement", ["edit", "delete", "other", "symlink"])
async def test_index_perime_avant_recherche_refuse(parametres, index_synthetique, changement):
    source = parametres.racine / "runbooks/postgres.md"
    if changement == "edit":
        source.write_text("# PostgreSQL indisponible\n\nNouvelle procédure.")
    elif changement == "delete":
        source.unlink()
    elif changement == "other":
        (source.parent / "other.md").write_text("# Other\n\nThis changes the whole corpus.")
    else:
        ancien = source.read_text()
        source.unlink()
        exterieur = parametres.racine / "outside.md"
        exterieur.write_text(ancien)
        source.symlink_to(exterieur)
    with pytest.raises(ValueError, match="provenance"):
        await Services(parametres).semantique("service")


@pytest.mark.asyncio
@pytest.mark.parametrize("etape", ["/v1/embeddings", "/collections/runbooks-current/points/query"])
@pytest.mark.parametrize("changement", ["edit", "delete", "restore", "replace", "other"])
async def test_mutation_pendant_requete_refuse_meme_si_texte_restaure(
    parametres, index_synthetique, etape, changement
):
    _, _, installer = index_synthetique
    source = parametres.racine / "runbooks/postgres.md"
    ancien = source.read_bytes()

    def modifier(requete):
        if requete.url.path != etape:
            return
        if changement == "delete":
            source.unlink()
        elif changement == "replace":
            temporaire = source.with_suffix(".tmp")
            temporaire.write_bytes(ancien)
            temporaire.replace(source)
        elif changement == "other":
            (source.parent / "other.md").write_text("# Other\n\nAnother runbook.")
        else:
            source.write_text("# New\n\nModified.")
            if changement == "restore":
                source.write_bytes(ancien)

    installer(modifier)
    with pytest.raises(ValueError, match="changé"):
        await Services(parametres).semantique("service")


@pytest.mark.asyncio
async def test_lecture_corpus_ne_bloque_pas_event_loop(parametres, monkeypatch, index_synthetique):
    from plateforme import services

    vrai_instantane = services.instantane_index
    boucle = threading.get_ident()
    appels = []

    def verifier(repertoire):
        appels.append(threading.get_ident())
        assert threading.get_ident() != boucle
        return vrai_instantane(repertoire)

    monkeypatch.setattr(services, "instantane_index", verifier)
    await Services(parametres).semantique("service")
    assert len(appels) == 2
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_annulation_ne_lance_pas_de_lectures_paralleles_et_recupere(
    parametres, monkeypatch, index_synthetique
):
    from plateforme import services

    vrai_instantane = services.instantane_index
    commence, liberer, termine = threading.Event(), threading.Event(), threading.Event()
    lectures = []

    def lecture_bloquee(repertoire):
        lectures.append(repertoire)
        commence.set()
        try:
            assert liberer.wait(5), "The test must release the bounded worker."
            return vrai_instantane(repertoire)
        finally:
            termine.set()

    monkeypatch.setattr(services, "instantane_index", lecture_bloquee)
    instance = Services(parametres)
    premiere = asyncio.create_task(instance.semantique("service"))
    try:
        assert await asyncio.to_thread(commence.wait, 2)
        premiere.cancel()
        with pytest.raises(asyncio.CancelledError):
            await premiere
        # The HTTP coroutine is cancelled but its worker still owns the read
        # lock. Subsequent requests fail promptly without queueing more reads.
        with pytest.raises(ValueError, match="déjà en cours"):
            await asyncio.wait_for(instance.semantique("service"), 1)
        assert len(lectures) == 1
        assert index_synthetique[1] == []
    finally:
        liberer.set()
        assert await asyncio.to_thread(termine.wait, 2)
    monkeypatch.setattr(services, "instantane_index", vrai_instantane)
    assert len(await instance.semantique("service")) == 1


@pytest.mark.asyncio
async def test_requetes_simultanees_serialisent_les_snapshots(
    parametres, monkeypatch, index_synthetique
):
    from plateforme import services

    vrai_instantane = services.instantane_index
    actifs, maximum = 0, 0
    garde = threading.Lock()

    def compter(repertoire):
        nonlocal actifs, maximum
        with garde:
            actifs += 1
            maximum = max(maximum, actifs)
        try:
            return vrai_instantane(repertoire)
        finally:
            with garde:
                actifs -= 1

    monkeypatch.setattr(services, "instantane_index", compter)
    instance = Services(parametres)
    resultats = await asyncio.gather(*(instance.semantique("service") for _ in range(5)))
    assert all(len(resultat) == 1 for resultat in resultats)
    assert maximum == 1


def test_api_refuse_index_perime_sans_exposer_charge(
    client, bearer, parametres, monkeypatch, index_synthetique
):
    monkeypatch.setattr(Services, "semantique", SEMANTIQUE_REELLE)
    point, appels, _ = index_synthetique
    valide = client.get("/api/recherche?q=service&mode=semantique", headers=bearer)
    assert valide.status_code == 200
    assert valide.json()["elements"][0]["donnees"] == point["payload"]
    point["payload"]["texte"] = "INTERNAL_SYNTHETIC_CONTENT_NEVER_RETURN"
    reponse = client.get("/api/recherche?q=service&mode=semantique", headers=bearer)
    assert reponse.status_code == 503
    assert reponse.json() == {
        "detail": ("Recherche sémantique indisponible. Vérifier l'index et l'inférence locale.")
    }
    assert "INTERNAL_SYNTHETIC" not in reponse.text
    assert "corpus_sha256" not in reponse.text
    # Reads only: no opportunistic reindex, write, collection mutation or fallback.
    assert {r.url.path for r in appels} == {
        "/v1/embeddings",
        "/collections/runbooks-current/points/query",
    }
