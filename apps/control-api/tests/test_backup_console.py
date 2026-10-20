"""Restore private console snapshots without exporting authentication state."""

import importlib.util
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
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
    monkeypatch.syspath_prepend(str(racine))
    resultats = {}
    for nom in ("memoire_sauvegarde", "sauvegarder", "tester_restauration"):
        spec = importlib.util.spec_from_file_location(nom, racine / (nom + ".py"))
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, nom, module)
        spec.loader.exec_module(module)
        resultats[nom] = module
    return SimpleNamespace(**resultats)


def memory_snapshot():
    first = "00000000-0000-4000-8000-000000000001"
    second = "00000000-0000-4000-8000-000000000002"
    return {
        "notes": [
            {
                "id": identifier,
                "scope": "synthetic",
                "titre": "Observation",
                "contenu": "Synthetic private evidence",
                "source": "Test fixture",
                "type": "fact",
                "cree_le": "2026-09-27T00:00:00+00:00",
                "maj_le": "2026-09-27T00:00:00+00:00",
            }
            for identifier in (first, second)
        ],
        "links": [{"from": second, "to": first}],
    }


def test_graph_backup_private_file_integrity_and_fixed_destination(scripts, tmp_path, monkeypatch):
    module = scripts.memoire_sauvegarde
    data = memory_snapshot()

    def query(client, statement):
        assert str(client.base_url) == "http://127.0.0.1:47474"
        assert "AmbicraftedNote" in statement
        return [{"row": [data]}]

    monkeypatch.setattr(module, "query", query)
    info = module.export(tmp_path, "synthetic-password")
    path = tmp_path / "memoire.json"
    assert path.stat().st_mode & 0o777 == 0o600
    assert info["notes"] == 2 and info["liens"] == 1
    assert b"synthetic-password" not in path.read_bytes()
    with pytest.raises(FileExistsError):
        module.export(tmp_path, "synthetic-password")
    path.write_text("{}")
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("Invalid backup must not start Docker"),
    )
    with pytest.raises(ValueError, match="checksum"):
        module.restore_check(tmp_path, info, "unused")


@pytest.mark.parametrize(
    "mutation", ["scope", "duplicate", "missing", "oversize", "identity", "self"]
)
def test_graph_backup_rejects_corrupt_or_cross_scope_context(scripts, mutation):
    data = memory_snapshot()
    if mutation == "scope":
        data["notes"][1]["scope"] = "another-client"
    elif mutation == "duplicate":
        data["notes"].append(data["notes"][0])
    elif mutation == "missing":
        data["notes"].pop()
    elif mutation == "oversize":
        data["notes"][0]["contenu"] = "x" * 4001
    elif mutation == "identity":
        data["notes"][0]["id"] = "invalid"
    else:
        data["links"][0]["from"] = data["links"][0]["to"]
    with pytest.raises(ValueError):
        scripts.memoire_sauvegarde.validate(data)


def test_memory_absence_requires_no_unlisted_file(scripts, tmp_path):
    module = scripts.memoire_sauvegarde
    assert module.export(tmp_path, None) == {"presente": False}
    assert module.restore_check(tmp_path, None, "unused") == {"memoire_presente": False}
    (tmp_path / "memoire.json").write_text("{}")
    with pytest.raises(ValueError, match="absent from manifest"):
        module.restore_check(tmp_path, None, "unused")


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


@pytest.mark.parametrize("mode", ["legacy", "grafana"])
def test_snapshot_capture_wal_et_normalise_seulement_destination(scripts, tmp_path, mode):
    source = tmp_path / "live.sqlite"
    destination = tmp_path / "snapshot.sqlite"
    with closing(
        base_privee(
            source,
            "PRAGMA journal_mode=WAL; PRAGMA wal_autocheckpoint=0;"
            "CREATE TABLE evidence(value TEXT);",
        )
    ) as live:
        live.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        live.execute("INSERT INTO evidence VALUES('committed-only-in-wal')")
        live.commit()
        assert Path(str(source) + "-wal").stat().st_size > 0
        with closing(sqlite3.connect(source.as_uri() + "?immutable=1", uri=True)) as raw:
            assert raw.execute("SELECT count(*) FROM evidence").fetchone()[0] == 0
        if mode == "legacy":
            with scripts.sauvegarder.sqlite_prive(source) as entree:
                scripts.sauvegarder.publier_sqlite(entree, destination)
        else:
            subprocess.run(
                [
                    sys.executable,
                    "-c",
                    scripts.sauvegarder.PROGRAMME_GRAFANA,
                    str(source),
                    str(destination),
                    str(os.getuid()),
                    str(os.getgid()),
                ],
                check=True,
                capture_output=True,
                timeout=10,
            )
        assert live.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert Path(str(source) + "-wal").stat().st_size > 0
    with closing(sqlite3.connect(destination.as_uri() + "?mode=ro", uri=True)) as copied:
        assert copied.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert copied.execute("SELECT value FROM evidence").fetchone() == (
            "committed-only-in-wal",
        )
    assert destination.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob("snapshot.sqlite-*"))


@pytest.mark.parametrize("nom", ["graphe.sqlite", "grafana.sqlite"])
def test_validation_ancienne_archive_wal_repetee_ne_modifie_aucun_fichier(
    scripts, tmp_path, nom
):
    from inventaire_sauvegarde import inventaire, verifier_inventaire

    path = tmp_path / nom
    with closing(
        base_privee(
            path,
            "PRAGMA journal_mode=WAL; CREATE TABLE evidence(value TEXT);"
            "INSERT INTO evidence VALUES('complete-closed-snapshot');",
        )
    ):
        pass
    assert not list(tmp_path.glob("*-wal"))
    assert path.read_bytes()[18:20] == b"\x02\x02"  # A closed legacy WAL snapshot.
    manifest = {"integrite": inventaire(tmp_path)}
    before = path.read_bytes()
    for _ in range(2):
        assert scripts.tester_restauration.verifier_sqlite(tmp_path) == {nom: True}
        verifier_inventaire(tmp_path, manifest)
        assert path.read_bytes() == before
        assert list(tmp_path.iterdir()) == [path]


def test_console_archive_wal_validation_repetee_sans_annexes(scripts, donnees):
    from inventaire_sauvegarde import inventaire, verifier_inventaire

    description = scripts.sauvegarder.copier_console(donnees.etat, donnees.destination)
    for path in donnees.destination.rglob("*.sqlite"):
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
    manifest = {"integrite": inventaire(donnees.destination)}
    for _ in range(2):
        result = scripts.tester_restauration.verifier_console(donnees.destination, description)
        assert result["analyses_console"] == 2 and result["checkpoints_console"] == 1
        verifier_inventaire(donnees.destination, manifest)


def test_snapshot_immutable_refuse_un_wal_actif(scripts, donnees):
    with (
        pytest.raises(ValueError, match="figé"),
        scripts.sauvegarder.sqlite_prive(donnees.etat / "console.sqlite", fige=True),
    ):
        pytest.fail("A live WAL database must never be treated as immutable")


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
