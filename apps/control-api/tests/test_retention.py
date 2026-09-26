"""Retention removes expired private state while preserving active work and outside paths."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from plateforme.depot import Introuvable


def creer_datee(moteur, statut, jours, *, identifiant=None):
    identifiant = identifiant or uuid.uuid4().hex
    moteur.depot.creer(identifiant, "Incident synthétique", "graphe", {}, "test")
    moteur.depot.changer(identifiant, statut, rapport={"message": "Synthétique"})
    date = (datetime.now(UTC) - timedelta(days=jours)).isoformat()
    with moteur.depot.connexion() as c:
        c.execute("UPDATE analyses SET cree_le=?,maj_le=? WHERE id=?", (date, date, identifiant))
    return identifiant


def test_retention_efface_terminaux_expirees_et_checkpoints(moteur):
    expires = [
        creer_datee(moteur, statut, 15)
        for statut in [
            "complet",
            "erreur",
            "interrompu",
            "annule",
            "rejete_par_humain",
            "budget_epuise",
            "en_attente_humain",
        ]
    ]
    for identifiant in expires:
        dossier = moteur.racine / identifiant
        dossier.mkdir(mode=0o700)
        (dossier / "graphe.sqlite").write_text("Checkpoint synthétique")
        moteur.depot.progression(identifiant, "termine")
        with moteur.depot.connexion() as c:
            c.execute("UPDATE analyses SET maj_le=cree_le WHERE id=?", (identifiant,))
    moteur.purger()
    for identifiant in expires:
        with pytest.raises(Introuvable):
            moteur.depot.obtenir(identifiant)
        assert not (moteur.racine / identifiant).exists()
    with moteur.depot.connexion() as c:
        assert c.execute("SELECT count(*) FROM evenements").fetchone()[0] == 0


def test_retention_preserve_actifs_et_analyses_recentes(moteur):
    conserves = [creer_datee(moteur, statut, 15) for statut in ["en_file", "en_cours", "decision"]]
    conserves += [creer_datee(moteur, statut, 1) for statut in ["complet", "en_attente_humain"]]
    moteur.purger()
    assert {a["id"] for a in moteur.depot.lister()["elements"]} == set(conserves)


def test_retention_ne_suit_pas_lien_de_checkpoint(moteur, tmp_path):
    identifiant = creer_datee(moteur, "complet", 15)
    exterieur = tmp_path / "exterieur"
    exterieur.mkdir()
    (exterieur / "conserver").write_text("Preuve synthétique")
    (moteur.racine / identifiant).symlink_to(exterieur, target_is_directory=True)
    moteur.purger()
    assert (exterieur / "conserver").read_text() == "Preuve synthétique"


def test_retention_chemin_non_uuid_ne_supprime_aucun_dossier_externe(moteur, tmp_path):
    exterieur = tmp_path / "conserver"
    exterieur.mkdir()
    (exterieur / "preuve").write_text("Préserver")
    creer_datee(moteur, "complet", 15, identifiant=str(exterieur))
    moteur.purger()
    assert (exterieur / "preuve").read_text() == "Préserver"


def test_retention_journal_et_revisions_30_jours(moteur):
    ancien = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    recent = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    with moteur.depot.connexion() as c:
        for date in [ancien, recent]:
            c.execute(
                "INSERT INTO journal(date,action,reference,acteur) VALUES(?,?,?,?)",
                (date, "test", None, "test"),
            )
            c.execute(
                "INSERT INTO revisions(nom,date,empreinte,contenu) VALUES(?,?,?,?)",
                ("test.md", date, "0" * 64, "Synthétique"),
            )
    moteur.purger()
    with moteur.depot.connexion() as c:
        assert c.execute("SELECT count(*) FROM journal WHERE action='test'").fetchone()[0] == 1
        assert c.execute("SELECT count(*) FROM revisions").fetchone()[0] == 1
        assert c.execute("SELECT date FROM revisions").fetchone()[0] == recent
