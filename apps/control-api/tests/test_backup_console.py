"""Restore private console snapshots without exporting authentication state."""

import importlib.util
import os
import sqlite3
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

IDENTIFIANT = "1234567890abcdef1234567890abcdef"
SECOND = "abcdef1234567890abcdef1234567890"
AUTH_SESSION = "fixture-session-must-never-reach-a-backup-file"
AUTH_TICKET = "fixture-ticket-must-never-reach-a-backup-file"


@pytest.fixture
def scripts(monkeypatch):
    racine = Path(__file__).resolve().parents[3] / "scripts"
    resultats = {}
    for nom in ("sauvegarder", "tester_restauration"):
        spec = importlib.util.spec_from_file_location(nom, racine / (nom + ".py"))
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, nom, module)
        spec.loader.exec_module(module)
        resultats[nom] = module
    return SimpleNamespace(**resultats)


def base_privee(chemin: Path, schema: str) -> sqlite3.Connection:
    fd = os.open(chemin, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    connexion = sqlite3.connect(chemin)
    connexion.executescript(schema)
    return connexion


@pytest.fixture
def donnees(tmp_path):
    etat = tmp_path / "etat"
    destination = tmp_path / "sauvegarde"
    etat.mkdir(mode=0o700)
    destination.mkdir(mode=0o700)
    console = base_privee(
        etat / "console.sqlite",
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE analyses(id TEXT PRIMARY KEY, titre TEXT);
        CREATE TABLE sessions(empreinte TEXT PRIMARY KEY, expire REAL);
        CREATE TABLE tickets(empreinte TEXT PRIMARY KEY, expire REAL);
    """,
    )
    console.execute("INSERT INTO analyses VALUES(?,?)", (IDENTIFIANT, "Alerte synthétique"))
    console.execute("INSERT INTO analyses VALUES(?,?)", (SECOND, "En file"))
    console.execute("INSERT INTO sessions VALUES(?,?)", (AUTH_SESSION, 42))
    console.execute("INSERT INTO tickets VALUES(?,?)", (AUTH_TICKET, 42))
    console.commit()
    analyses = etat / "analyses"
    analyses.mkdir(mode=0o700)
    repertoire = analyses / IDENTIFIANT
    repertoire.mkdir(mode=0o700)
    graphe = base_privee(
        repertoire / "graphe.sqlite",
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE checkpoints(id INTEGER PRIMARY KEY, valeur TEXT);
        INSERT INTO checkpoints(valeur) VALUES('état synthétique');
    """,
    )
    graphe.commit()
    yield SimpleNamespace(
        etat=etat, destination=destination, console=console, graphe=graphe, repertoire=repertoire
    )
    console.close()
    graphe.close()


def test_copie_wal_coherente_et_auth_jamais_exportee(scripts, donnees):
    donnees.console.execute("INSERT INTO analyses VALUES(?,?)", ("f" * 32, "non validé"))
    description = scripts.sauvegarder.copier_console(donnees.etat, donnees.destination)
    assert description["analyses"] == 2
    assert description["sans_checkpoint"] == 1
    assert len(description["checkpoints"]) == 1
    assert description["atomicite_multi_bases"] is False
    copie = donnees.destination / "console/console.sqlite"
    with sqlite3.connect(copie) as c:
        assert c.execute("SELECT count(*) FROM analyses").fetchone()[0] == 2
        assert c.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM tickets").fetchone()[0] == 0
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    for fichier in donnees.destination.rglob("*"):
        if fichier.is_file():
            assert AUTH_SESSION.encode() not in fichier.read_bytes()
            assert AUTH_TICKET.encode() not in fichier.read_bytes()
            assert fichier.stat().st_mode & 0o777 == 0o600
        else:
            assert fichier.stat().st_mode & 0o777 == 0o700
    assert donnees.console.execute("SELECT count(*) FROM sessions").fetchone()[0] == 1
    assert donnees.console.execute("SELECT count(*) FROM tickets").fetchone()[0] == 1
    assert "Alerte" not in str(description)


def test_restauration_jetable_compte_sans_toucher_source(scripts, donnees):
    description = scripts.sauvegarder.copier_console(donnees.etat, donnees.destination)
    resultat = scripts.tester_restauration.verifier_console(donnees.destination, description)
    assert resultat == {
        "console_presente": True,
        "analyses_console": 2,
        "checkpoints_console": 1,
        "sessions_console": 0,
        "tickets_console": 0,
        "sqlite_console": True,
        "atomicite_multi_bases": False,
    }
    assert donnees.console.execute("SELECT count(*) FROM sessions").fetchone()[0] == 1
    assert donnees.graphe.execute("SELECT count(*) FROM checkpoints").fetchone()[0] == 1


def test_console_absente_et_sauvegarde_ancienne(scripts, tmp_path):
    resultat = scripts.sauvegarder.copier_console(tmp_path / "absent", tmp_path)
    assert not resultat["presente"]
    assert not scripts.tester_restauration.verifier_console(tmp_path, None)["console_presente"]
    assert not scripts.tester_restauration.verifier_console(tmp_path, resultat)["console_presente"]


def test_dossier_etat_sans_base(scripts, tmp_path):
    assert not scripts.sauvegarder.copier_console(tmp_path, tmp_path)["presente"]


def test_identifiant_sqlite_invalide_ne_devient_pas_chemin(scripts, donnees):
    donnees.console.execute("INSERT INTO analyses VALUES(?,?)", ("../../exterieur", "fixture"))
    donnees.console.commit()
    with pytest.raises(ValueError, match="Identifiant"):
        scripts.sauvegarder.copier_console(donnees.etat, donnees.destination)
    assert not (donnees.destination / "console").exists()


@pytest.mark.parametrize(
    "chemin",
    [
        "console.sqlite",
        "analyses",
        f"analyses/{IDENTIFIANT}",
        f"analyses/{IDENTIFIANT}/graphe.sqlite",
    ],
)
def test_sources_symlinks_refusees(scripts, donnees, tmp_path, chemin):
    donnees.console.close()
    donnees.graphe.close()
    original = donnees.etat / chemin
    deplace = tmp_path / "deplace"
    original.rename(deplace)
    original.symlink_to(deplace, target_is_directory=deplace.is_dir())
    with pytest.raises((ValueError, OSError)):
        scripts.sauvegarder.copier_console(donnees.etat, donnees.destination)


def test_journal_symlink_refuse(scripts, donnees, tmp_path):
    donnees.console.close()
    externe = tmp_path / "wal-externe"
    externe.write_bytes(b"fixture")
    externe.chmod(0o600)
    (donnees.etat / "console.sqlite-wal").symlink_to(externe)
    with pytest.raises(ValueError, match="Journal"):
        scripts.sauvegarder.copier_console(donnees.etat, donnees.destination)


@pytest.mark.parametrize("chemin", ["", "console.sqlite"])
def test_etat_public_refuse(scripts, donnees, chemin):
    (donnees.etat / chemin).chmod(0o755 if not chemin else 0o644)
    with pytest.raises(ValueError, match="priv"):
        scripts.sauvegarder.copier_console(donnees.etat, donnees.destination)


def test_orphelin_ignore_et_destination_non_ecrasee(scripts, donnees):
    orphelin = donnees.etat / "analyses" / ("e" * 32)
    orphelin.mkdir(mode=0o700)
    (orphelin / "graphe.sqlite").write_text("ne pas lire")
    description = scripts.sauvegarder.copier_console(donnees.etat, donnees.destination)
    assert len(description["checkpoints"]) == 1
    with pytest.raises(FileExistsError):
        scripts.sauvegarder.copier_console(donnees.etat, donnees.destination)


@pytest.mark.parametrize(
    "champ,valeur",
    [
        ("fichier", "../console.sqlite"),
        ("analyses", 99),
        ("sans_checkpoint", -1),
        ("sessions_exclues", False),
        ("atomicite_multi_bases", True),
    ],
)
def test_manifeste_console_altere_refuse(scripts, donnees, champ, valeur):
    description = scripts.sauvegarder.copier_console(donnees.etat, donnees.destination)
    description[champ] = valeur
    with pytest.raises(ValueError):
        scripts.tester_restauration.verifier_console(donnees.destination, description)


@pytest.mark.parametrize("variation", ["chemin", "identifiant", "doublon"])
def test_checkpoint_manifeste_altere_refuse(scripts, donnees, variation):
    description = scripts.sauvegarder.copier_console(donnees.etat, donnees.destination)
    if variation == "chemin":
        description["checkpoints"][0]["fichier"] = "../../exterieur.sqlite"
    elif variation == "identifiant":
        description["checkpoints"][0]["analyse_id"] = "../../exterieur"
    else:
        description["checkpoints"].append(deepcopy(description["checkpoints"][0]))
    with pytest.raises(ValueError):
        scripts.tester_restauration.verifier_console(donnees.destination, description)


def test_restauration_refuse_tout_jeton_reintroduit(scripts, donnees):
    description = scripts.sauvegarder.copier_console(donnees.etat, donnees.destination)
    with sqlite3.connect(donnees.destination / "console/console.sqlite") as c:
        c.execute("INSERT INTO tickets VALUES(?,?)", (AUTH_TICKET, 42))
    with pytest.raises(ValueError, match="authentification"):
        scripts.tester_restauration.verifier_console(donnees.destination, description)


def test_checkpoint_corrompu_refuse(scripts, donnees):
    description = scripts.sauvegarder.copier_console(donnees.etat, donnees.destination)
    (donnees.destination / description["checkpoints"][0]["fichier"]).write_bytes(b"corrompu")
    with pytest.raises(sqlite3.DatabaseError):
        scripts.tester_restauration.verifier_console(donnees.destination, description)


def test_base_fifo_refusee_sans_blocage(scripts, donnees):
    donnees.console.close()
    chemin = donnees.etat / "console.sqlite"
    chemin.unlink()
    os.mkfifo(chemin, 0o600)
    with pytest.raises(ValueError, match="régulière"):
        scripts.sauvegarder.copier_console(donnees.etat, donnees.destination)


def test_console_presente_non_declaree_refusee(scripts, donnees):
    scripts.sauvegarder.copier_console(donnees.etat, donnees.destination)
    for description in (None, {"presente": False}):
        with pytest.raises(ValueError, match="absente du manifeste"):
            scripts.tester_restauration.verifier_console(donnees.destination, description)
