"""Actual encrypted recovery and hostile archive/source boundaries, all synthetic."""

import importlib
import io
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def recovery(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "scripts"))
    return SimpleNamespace(
        **{
            name: importlib.import_module(name)
            for name in (
                "inventaire_sauvegarde",
                "exporter_sauvegarde",
                "exercer_recuperation",
            )
        }
    )


@pytest.fixture
def source(tmp_path, recovery):
    corpus, mission, backup = [tmp_path / name for name in ("corpus", "mission", "backup")]
    for directory in (corpus, mission, backup):
        directory.mkdir(mode=0o700)
    (corpus / "a.md").write_text("# Runbook\n\nVerify, do not execute blindly.\n")
    (corpus / ".private.md").write_text("Not an active indexed source")
    (corpus / "excluded.txt").write_text("Not a Markdown runbook")
    (mission / "sub").mkdir(mode=0o700)
    (mission / "sub/report.csv").write_text("status\nsynthetic\n")
    inventory = recovery.inventaire_sauvegarde
    description = inventory.copier_sources(corpus, [mission], backup)
    manifest = {
        "type": "platform-backup-v1",
        "complet": True,
        "sources": description,
        "integrite": inventory.inventaire(backup),
    }
    (backup / "manifest.json").write_text(json.dumps(manifest))
    (backup / "manifest.json").chmod(0o600)
    return SimpleNamespace(corpus=corpus, mission=mission, backup=backup, manifest=manifest)


def test_complete_sources_private_and_no_unindexed_data(source, recovery):
    inventory = recovery.inventaire_sauvegarde
    assert inventory.verifier_inventaire(source.backup, source.manifest)["fichiers_verifies"] == 2
    assert source.manifest["sources"]["fichiers"] == 2
    assert (
        source.backup / "sources/missions/00/sub/report.csv"
    ).read_text() == "status\nsynthetic\n"
    assert not (source.backup / "sources/runbooks/.private.md").exists()
    for path in source.backup.rglob("*"):
        assert path.stat().st_mode & 0o077 == 0


@pytest.mark.parametrize("mutation", ["tamper", "extra", "missing", "duplicate", "traversal"])
def test_integrity_catches_all_inventory_changes(source, recovery, mutation):
    if mutation == "tamper":
        (source.backup / "sources/runbooks/a.md").write_text("tampered")
    elif mutation == "extra":
        (source.backup / "extra").write_text("not listed")
        (source.backup / "extra").chmod(0o600)
    elif mutation == "missing":
        (source.backup / "sources/runbooks/a.md").unlink()
    elif mutation == "duplicate":
        source.manifest["integrite"].append(source.manifest["integrite"][0])
    else:
        source.manifest["integrite"][0]["fichier"] = "../elsewhere"
    with pytest.raises(ValueError, match="inventory|checksum"):
        recovery.inventaire_sauvegarde.verifier_inventaire(source.backup, source.manifest)


@pytest.mark.parametrize(
    "kind", ["symlink", "fifo", "directory-link", "oversize", "world-writable"]
)
def test_unsafe_sources_fail_closed_without_hanging(source, recovery, tmp_path, kind):
    bad = source.mission / "untrusted"
    if kind == "symlink":
        bad.symlink_to(source.corpus / "a.md")
    elif kind == "directory-link":
        bad.symlink_to(source.corpus, target_is_directory=True)
    elif kind == "fifo":
        os.mkfifo(bad)
    elif kind == "world-writable":
        bad.write_text("bad")
        bad.chmod(0o666)
    else:
        with bad.open("wb") as output:
            output.truncate(recovery.inventaire_sauvegarde.MAX_SOURCE_FILE + 1)
    destination = tmp_path / "second"
    destination.mkdir(mode=0o700)
    with pytest.raises((ValueError, OSError)):
        recovery.inventaire_sauvegarde.copier_sources(source.corpus, [source.mission], destination)


def test_backup_source_overlap_refused(source, recovery):
    destination = source.mission / "inside"
    destination.mkdir(mode=0o700)
    with pytest.raises(ValueError, match="overlap"):
        recovery.inventaire_sauvegarde.copier_sources(source.corpus, [source.mission], destination)


@pytest.mark.parametrize(
    "kind", ["traversal", "absolute", "link", "hardlink", "fifo", "duplicate", "pax", "truncated"]
)
def test_hostile_tar_never_escapes_private_stage(recovery, tmp_path, kind):
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        name = "../escaped" if kind == "traversal" else "/escaped" if kind == "absolute" else "data"
        entry = tarfile.TarInfo(name)
        entry.size = 1
        if kind in {"link", "hardlink", "fifo", "pax"}:
            entry.type = {
                "link": tarfile.SYMTYPE,
                "hardlink": tarfile.LNKTYPE,
                "fifo": tarfile.FIFOTYPE,
                "pax": tarfile.XHDTYPE,
            }[kind]
            entry.linkname = "../escaped"
            entry.size = 0
        archive.addfile(entry, io.BytesIO(b"a"))
        if kind == "duplicate":
            archive.addfile(entry, io.BytesIO(b"b"))
    encoded = payload.getvalue()
    if kind == "truncated":
        encoded = encoded[:513]
    destination = tmp_path / "stage"
    destination.mkdir(mode=0o700)
    with pytest.raises((ValueError, tarfile.TarError)):
        recovery.exporter_sauvegarde.extraire(io.BytesIO(encoded), destination)
    assert not (tmp_path / "escaped").exists()


def test_legacy_backup_readable_but_not_qualified_export(source, recovery):
    source.manifest.pop("integrite")
    inventory = recovery.inventaire_sauvegarde
    assert inventory.verifier_inventaire(source.backup, source.manifest) == {
        "integrite_verifiee": False,
        "format_ancien": True,
    }
    with pytest.raises(ValueError, match="integrity"):
        inventory.verifier_inventaire(source.backup, source.manifest, obligatoire=True)


@pytest.fixture
def keys(tmp_path):
    if not shutil.which("age") or not shutil.which("age-keygen"):
        pytest.skip("Real age integration requires the qualified executable")
    identity, recipients = tmp_path / "key.txt", tmp_path / "recipients.txt"
    subprocess.run(["age-keygen", "-o", str(identity)], capture_output=True, check=True, timeout=10)
    identity.chmod(0o600)
    recipients.write_bytes(
        subprocess.run(
            ["age-keygen", "-y", str(identity)],
            capture_output=True,
            check=True,
            timeout=10,
        ).stdout
    )
    recipients.chmod(0o600)
    return identity, recipients


def test_real_age_roundtrip_tampering_wrong_key_and_existing_destination(
    source, recovery, keys, tmp_path
):
    module = recovery.exporter_sauvegarde
    identity, recipients = keys
    ciphertext = tmp_path / "backup.age"
    encrypted = module.chiffrer(source.backup, recipients, ciphertext)
    assert encrypted["copie_hors_poste_verifiee"] is False
    assert b"Verify, do not execute blindly" not in ciphertext.read_bytes()
    restored = tmp_path / "restored"
    module.dechiffrer(ciphertext, identity, restored)
    assert (restored / "sources/runbooks/a.md").read_bytes() == (
        source.corpus / "a.md"
    ).read_bytes()
    original = ciphertext.read_bytes()
    with pytest.raises(FileExistsError):
        module.chiffrer(source.backup, recipients, ciphertext)
    assert ciphertext.read_bytes() == original
    with pytest.raises(FileExistsError):
        module.dechiffrer(ciphertext, identity, restored)
    wrong = tmp_path / "wrong.txt"
    subprocess.run(["age-keygen", "-o", str(wrong)], capture_output=True, check=True, timeout=10)
    wrong.chmod(0o600)
    with pytest.raises(subprocess.CalledProcessError):
        module.dechiffrer(ciphertext, wrong, tmp_path / "wrong-output")
    assert not (tmp_path / "wrong-output").exists()
    ciphertext.write_bytes(original[:-8] + bytes(x ^ 255 for x in original[-8:]))
    with pytest.raises(subprocess.CalledProcessError):
        module.dechiffrer(ciphertext, identity, tmp_path / "tampered-output")
    assert not (tmp_path / "tampered-output").exists()
    assert not list(tmp_path.glob("platform-decrypt-*"))


def test_nonempty_production_state_checkpoint_and_conversation_survive_real_encryption(
    recovery, keys, tmp_path
):
    mask = os.umask(0o077)
    try:
        result = recovery.exercer_recuperation.exercer(tmp_path)
    finally:
        os.umask(mask)
    assert result["analyses_console"] == result["checkpoints_console"] == 1
    assert result["contenu_console"]["conversations"] == 1
    assert result["contenu_console"]["messages_conversation"] == 2
    assert result["contenu_console"]["pieces_conversation"] == 1
    assert result["sessions_console"] == result["tickets_console"] == 0
    assert result["mission_relue"] and result["checkpoint_langgraph_relu"]
    assert result["notes_memoire"] == 2 and result["liens_memoire"] == 1
    assert result["neo4j_restaure"] is False  # Separate opt-in Docker integration, never simulated.


def test_scheduled_export_requires_complete_configuration_and_propagates_failure(
    source, recovery, monkeypatch, tmp_path
):
    backup = importlib.import_module("sauvegarder")
    for name in ("PLATFORM_BACKUP_AGE_RECIPIENTS_FILE", "PLATFORM_BACKUP_EXPORT_DIR"):
        monkeypatch.delenv(name, raising=False)
    assert backup.exporter_si_configure(source.backup, {}) == {"export_configure": False}
    with pytest.raises(ValueError, match="paramètres"):
        backup.exporter_si_configure(source.backup, {"PLATFORM_BACKUP_EXPORT_DIR": str(tmp_path)})
    calls = []

    def fail(*args):
        calls.append(args)
        raise OSError("synthetic unavailable destination")

    monkeypatch.setattr(recovery.exporter_sauvegarde, "chiffrer", fail)
    with pytest.raises(OSError):
        backup.exporter_si_configure(
            source.backup,
            {
                "PLATFORM_BACKUP_EXPORT_DIR": str(tmp_path),
                "PLATFORM_BACKUP_AGE_RECIPIENTS_FILE": str(tmp_path / "recipients.txt"),
            },
        )
    assert calls[0][2] == tmp_path / "backup.tar.age"


def test_orphan_conversation_is_not_a_successful_restore(recovery, tmp_path):
    from sauvegarder import copier_console
    from tester_restauration import verifier_console

    from plateforme.conversations import Conversations
    from plateforme.depot import Depot

    depot = Depot(tmp_path / "state")
    conversations = Conversations(depot)
    thread = conversations.creer()["id"]
    conversations.enregistrer_tour(
        thread, "op", "synthetic question", {"texte": "synthetic answer"}
    )
    with depot.connexion() as connection:
        connection.execute("DELETE FROM conversations WHERE id=?", (thread,))
    backup = tmp_path / "backup"
    backup.mkdir(mode=0o700)
    description = copier_console(tmp_path / "state", backup)
    with pytest.raises(ValueError, match="orphelin"):
        verifier_console(backup, description)
