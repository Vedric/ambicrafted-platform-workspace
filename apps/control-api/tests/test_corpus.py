"""Real-filesystem confinement, bounded reads and concurrent human edits."""

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from plateforme.corpus import Corpus
from plateforme.depot import Conflit, Introuvable


@pytest.fixture
def corpus(parametres, depot):
    return Corpus(parametres.racine / "runbooks", depot)


@pytest.mark.parametrize(
    "nom",
    [
        "../prive.md",
        "/tmp/prive.md",
        "a/b.md",
        "..md",
        ".cache.md",
        "a\\b.md",
        "a.MD",
        "a.md\x00",
        "a.md/../b.md",
        "a b.md",
        "a" * 117 + ".md",
        "é.md",
    ],
)
def test_nom_ne_peut_pas_sortir_du_corpus(corpus, nom):
    with pytest.raises(ValueError):
        corpus.lire(nom)
    with pytest.raises(ValueError):
        corpus.ecrire(nom, "# Test", "", "operateur")


def test_lecture_empreinte_exacte_et_liste_metadata(corpus):
    document = corpus.lire("postgres.md")
    assert document["empreinte"] == hashlib.sha256(document["contenu"].encode()).hexdigest()
    assert document["octets"] == len(document["contenu"].encode())
    assert document["titre"] == "PostgreSQL indisponible"
    liste = corpus.lister("POSTGRESQL")
    assert len(liste) == 1
    assert "contenu" not in liste[0]
    assert liste[0]["extrait"].startswith("# PostgreSQL")
    assert corpus.lister("sans correspondance") == []


def test_inexistant(corpus):
    with pytest.raises(Introuvable):
        corpus.lire("absent.md")


def test_lien_symbolique_refuse_lecture_et_edition(corpus, tmp_path):
    exterieur = tmp_path / "prive.md"
    exterieur.write_text("Confidentiel synthétique")
    (corpus.racine / "lien.md").symlink_to(exterieur)
    with pytest.raises((ValueError, OSError)):
        corpus.lire("lien.md")
    with pytest.raises((ValueError, OSError)):
        corpus.ecrire("lien.md", "# Remplacement", "", "operateur")
    assert exterieur.read_text() == "Confidentiel synthétique"
    assert all(d["nom"] != "lien.md" for d in corpus.lister())


def test_racine_symbolique_refuse_lecture_et_edition(corpus, tmp_path):
    lien = tmp_path / "lien-corpus"
    lien.symlink_to(corpus.racine, target_is_directory=True)
    autre = Corpus(lien, corpus.depot)
    with pytest.raises((OSError, ValueError)):
        autre.lire("postgres.md")
    with pytest.raises((OSError, ValueError)):
        autre.ecrire("nouveau.md", "# Test", "", "operateur")


def test_fifo_rejete_sans_blocage(corpus):
    os.mkfifo(corpus.racine / "pipe.md")
    with pytest.raises(ValueError, match="non régulier"):
        corpus.lire("pipe.md")
    assert all(d["nom"] != "pipe.md" for d in corpus.lister())


def test_fichier_trop_grand_et_utf8_invalide_refuses(corpus):
    (corpus.racine / "gros.md").write_bytes(b"x" * 32_001)
    with pytest.raises(ValueError, match="volumineux"):
        corpus.lire("gros.md")
    (corpus.racine / "invalide.md").write_bytes(b"\xff")
    with pytest.raises(UnicodeError):
        corpus.lire("invalide.md")


@pytest.mark.parametrize("texte", ["", "  \n ", "x" * 8001, "😀" * 8001])
def test_edition_taille_bornee(corpus, texte):
    with pytest.raises(ValueError):
        corpus.ecrire("nouveau.md", texte, "", "operateur")
    assert not (corpus.racine / "nouveau.md").exists()


def test_creation_edition_et_conflit_optimiste(corpus):
    premier = corpus.ecrire("nouveau.md", "# Premier\n", "", "operateur")
    second = corpus.ecrire("nouveau.md", "# Second\n", premier["empreinte"], "operateur")
    with pytest.raises(Conflit):
        corpus.ecrire("nouveau.md", "# Obsolète", premier["empreinte"], "operateur")
    assert corpus.lire("nouveau.md") == second
    assert (corpus.racine / "nouveau.md").stat().st_mode & 0o077 == 0
    assert not list(corpus.racine.glob(".edition-*"))
    with corpus.depot.connexion() as c:
        assert (
            c.execute("SELECT contenu FROM revisions WHERE nom='nouveau.md'").fetchone()[0]
            == "# Premier\n"
        )


def test_fichier_disparu_refuse_empreinte_obsolete(corpus):
    with pytest.raises(Conflit):
        corpus.ecrire("absent.md", "# Test", "0" * 64, "operateur")
    assert not (corpus.racine / "absent.md").exists()


def test_editions_concurrentes_une_seule_gagne(corpus):
    original = corpus.lire("postgres.md")

    def modifier(i):
        try:
            corpus.ecrire("postgres.md", f"# Révision {i}", original["empreinte"], "operateur")
            return True
        except Conflit:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(modifier, range(2))) == [False, True]


def test_historique_revisions_borne(corpus):
    courant = corpus.lire("postgres.md")
    for i in range(15):
        courant = corpus.ecrire("postgres.md", f"# Version {i}", courant["empreinte"], "operateur")
    with corpus.depot.connexion() as c:
        lignes = c.execute("SELECT contenu FROM revisions ORDER BY id").fetchall()
    assert len(lignes) == 10
    assert lignes[0][0] == "# Version 4"
    assert lignes[-1][0] == "# Version 13"
