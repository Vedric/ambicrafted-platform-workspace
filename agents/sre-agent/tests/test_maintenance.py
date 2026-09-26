"""Operational contracts: private credentials and narrowly scoped deletion."""

from datetime import UTC, datetime, timedelta
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def charger(nom):
    racine = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(nom, racine / "scripts" / f"{nom}.py")
    module = importlib.util.module_from_spec(spec)
    # Match direct script execution: sibling maintenance modules are importable.
    with pytest.MonkeyPatch.context() as patch:
        patch.syspath_prepend(str(racine / "scripts"))
        spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o666])
def test_environnement_refuse_permissions_publiques(tmp_path, mode):
    plateforme = charger("plateforme")
    fichier = tmp_path / "config"
    fichier.write_text("TEST=synthetic\n")
    fichier.chmod(mode)
    with pytest.raises(ValueError):
        plateforme.environnement(fichier)


def test_environnement_refuse_lien(tmp_path):
    plateforme = charger("plateforme")
    fichier = tmp_path / "config"
    fichier.write_text("TEST=synthetic\n")
    fichier.chmod(0o600)
    lien = tmp_path / "link"
    lien.symlink_to(fichier)
    with pytest.raises(ValueError):
        plateforme.environnement(lien)


def test_cles_existantes_preservees_sans_requete(tmp_path, monkeypatch):
    plateforme = charger("plateforme")
    monkeypatch.setattr(plateforme, "RACINE", tmp_path)
    (tmp_path / "gateway").mkdir()
    for nom, texte in {
        "gateway/.env": "LITELLM_MASTER_KEY=fixture-master\n",
        ".env": "CONFIDENTIAL_KEY=fixture-local\nORCHESTRATOR_KEY=fixture-public\n",
    }.items():
        fichier = tmp_path / nom
        fichier.write_text(texte)
        fichier.chmod(0o600)
    original = (tmp_path / ".env").read_bytes()
    resultat = plateforme.creer_cles(True)
    assert set(resultat.values()) == {"conservée"}
    assert (tmp_path / ".env").read_bytes() == original


def test_creation_cle_privee_sans_exposer_sa_valeur(tmp_path, monkeypatch, capsys):
    plateforme = charger("plateforme")
    monkeypatch.setattr(plateforme, "RACINE", tmp_path)
    (tmp_path / "gateway").mkdir()
    maitre = tmp_path / "gateway/.env"
    maitre.write_text("LITELLM_MASTER_KEY=fixture-master\n")
    maitre.chmod(0o600)
    (tmp_path / ".env.example").write_text("CONFIDENTIAL_KEY=\n")
    requetes = []

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            requetes.append(kwargs["json"])
            return SimpleNamespace(
                raise_for_status=lambda: None, json=lambda: {"key": "fixture-created"}
            )

    monkeypatch.setattr(plateforme.httpx, "Client", Client)
    resultat = plateforme.creer_cles(False)
    assert requetes[0]["models"] == ["local", "local-embed"]
    assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600
    assert plateforme.environnement(tmp_path / ".env")["CONFIDENTIAL_KEY"] == "fixture-created"
    assert "fixture-created" not in json.dumps(resultat) + capsys.readouterr().out


def test_purge_limitee_aux_anciennes_sauvegardes_reconnues(tmp_path, monkeypatch):
    sauvegarde = charger("sauvegarder")
    destination = tmp_path / "backups"
    destination.mkdir()
    monkeypatch.setattr(sauvegarde, "DESTINATION", destination)
    vieux = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    recent = datetime.now(UTC).isoformat()
    for nom, genre, date in [
        ("20200101T000000Z", "platform-backup-v1", vieux),
        ("20200102T000000Z", "foreign-backup", vieux),
        ("20200103T000000Z", "platform-backup-v1", recent),
        ("unrelated", "platform-backup-v1", vieux),
    ]:
        dossier = destination / nom
        dossier.mkdir()
        (dossier / "manifest.json").write_text(json.dumps({"type": genre, "date": date}))
    externe = tmp_path / "external"
    externe.mkdir()
    (externe / "manifest.json").write_text(
        json.dumps({"type": "platform-backup-v1", "date": vieux})
    )
    (destination / "20200104T000000Z").symlink_to(externe, target_is_directory=True)
    assert sauvegarde.purger(14) == 1
    assert not (destination / "20200101T000000Z").exists()
    assert len(list(destination.iterdir())) == 4
    assert externe.is_dir()


def test_purge_refuse_retention_nulle(tmp_path, monkeypatch):
    sauvegarde = charger("sauvegarder")
    monkeypatch.setattr(sauvegarde, "DESTINATION", tmp_path)
    with pytest.raises(ValueError):
        sauvegarde.purger(0)


def test_restauration_incomplete_ne_lance_pas_docker(tmp_path, monkeypatch):
    restauration = charger("tester_restauration")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"type": "platform-backup-v1", "complet": False})
    )
    monkeypatch.setattr(restauration, "commande", lambda *a, **k: pytest.fail("Docker lancé"))
    with pytest.raises(ValueError):
        restauration.verifier(tmp_path)
