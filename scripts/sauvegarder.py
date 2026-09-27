# /// script
# requires-python = ">=3.14"
# dependencies = ["httpx==0.28.1", "python-dotenv==1.2.3"]
# ///
"""Sauvegarde locale cohérente ; secrets et données restent dans un dossier 0700."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
DESTINATION = Path.home() / ".local/state/platform-backups"


def verifier_dossier_prive(chemin: Path) -> None:
    """Reject links and public state directories before opening any database."""
    if not chemin.is_absolute() or chemin.resolve() != chemin:
        raise ValueError("Dossier absolu sans lien symbolique requis.")
    info = chemin.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("Dossier privé appartenant à cet utilisateur requis.")


@contextmanager
def sqlite_prive(chemin: Path):
    """Pin the parent directory while SQLite reads the database and its live WAL."""
    verifier_dossier_prive(chemin.parent)
    parent = os.open(chemin.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    descripteur = None
    connexion = None
    try:
        descripteur = os.open(
            chemin.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
        )
        info = os.fstat(descripteur)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
        ):
            raise ValueError("Base SQLite privée régulière requise.")
        for suffixe in ("-wal", "-shm", "-journal"):
            try:
                annexe = os.stat(
                    chemin.name + suffixe, dir_fd=parent, follow_symlinks=False
                )
            except FileNotFoundError:
                continue
            if (
                not stat.S_ISREG(annexe.st_mode)
                or annexe.st_uid != os.getuid()
                or annexe.st_mode & 0o077
            ):
                raise ValueError("Journal SQLite privé régulier requis.")
        # A descriptor for the *directory* keeps the -wal/-shm lookup beside the source.
        uri = Path(f"/proc/self/fd/{parent}/{chemin.name}").as_uri() + "?mode=ro"
        connexion = sqlite3.connect(uri, uri=True, timeout=5)
        actuel = os.stat(chemin.name, dir_fd=parent, follow_symlinks=False)
        if (actuel.st_dev, actuel.st_ino) != (info.st_dev, info.st_ino):
            raise ValueError("La base SQLite a changé pendant son ouverture.")
        connexion.execute("PRAGMA query_only=ON")
        yield connexion
    finally:
        if connexion is not None:
            connexion.close()
        if descripteur is not None:
            os.close(descripteur)
        os.close(parent)


def publier_sqlite(entree: sqlite3.Connection, chemin: Path) -> None:
    """Create a private destination exclusively; never replace an operator file."""
    verifier_dossier_prive(chemin.parent)
    fd = os.open(chemin, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    termine = False
    sortie = sqlite3.connect(chemin)
    try:
        entree.backup(sortie)
        if sortie.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("La copie SQLite est incohérente.")
        sortie.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        sortie.execute("PRAGMA journal_mode=DELETE")
        termine = True
    finally:
        sortie.close()
        if not termine:
            chemin.unlink(missing_ok=True)
    chemin.chmod(0o600)


def copier_console(etat: Path, destination: Path) -> dict:
    """Snapshot each database separately; auth sessions never reach the backup disk."""
    verifier_dossier_prive(destination)
    resultat = {
        "presente": False,
        "analyses": 0,
        "checkpoints": [],
        "sans_checkpoint": 0,
        "sessions_exclues": True,
        "coherence": "sqlite_individuelle",
        "atomicite_multi_bases": False,
    }
    if not etat.exists() and not etat.is_symlink():
        return resultat
    verifier_dossier_prive(etat)
    source = etat / "console.sqlite"
    if not source.exists() and not source.is_symlink():
        return resultat
    copie = sqlite3.connect(":memory:")
    try:
        with sqlite_prive(source) as entree:
            entree.backup(copie)
        copie.execute("PRAGMA secure_delete=ON")
        for table in ("sessions", "tickets"):
            copie.execute(f"DELETE FROM {table}")
        copie.commit()
        copie.execute("VACUUM")
        identifiants = [
            r[0] for r in copie.execute("SELECT id FROM analyses ORDER BY id")
        ]
        if any(
            not isinstance(i, str) or not re.fullmatch(r"[0-9a-f]{32}", i)
            for i in identifiants
        ):
            raise ValueError("Identifiant d’analyse invalide dans la console.")
        dossier = destination / "console"
        dossier.mkdir(mode=0o700)
        publier_sqlite(copie, dossier / "console.sqlite")
    finally:
        copie.close()
    resultat.update(
        presente=True, fichier="console/console.sqlite", analyses=len(identifiants)
    )
    source_analyses = etat / "analyses"
    if source_analyses.exists() or source_analyses.is_symlink():
        verifier_dossier_prive(source_analyses)
    for identifiant in identifiants:
        repertoire = source_analyses / identifiant
        if not repertoire.exists() and not repertoire.is_symlink():
            resultat["sans_checkpoint"] += 1
            continue
        verifier_dossier_prive(repertoire)
        checkpoint = repertoire / "graphe.sqlite"
        if not checkpoint.exists() and not checkpoint.is_symlink():
            resultat["sans_checkpoint"] += 1
            continue
        cible = dossier / "analyses" / identifiant
        (dossier / "analyses").mkdir(mode=0o700, exist_ok=True)
        cible.mkdir(mode=0o700)
        with sqlite_prive(checkpoint) as entree:
            publier_sqlite(entree, cible / "graphe.sqlite")
        resultat["checkpoints"].append(
            {
                "analyse_id": identifiant,
                "fichier": f"console/analyses/{identifiant}/graphe.sqlite",
            }
        )
    return resultat


def sauvegarder() -> Path:
    import httpx
    from dotenv import dotenv_values
    from memoire_sauvegarde import export as exporter_memoire

    os.umask(0o077)
    dossier = DESTINATION / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dossier.mkdir(mode=0o700, parents=True)
    manifeste = {
        "type": "platform-backup-v1",
        "date": datetime.now(UTC).isoformat(),
        "complet": False,
    }
    fichier_manifeste = dossier / "manifest.json"
    fichier_manifeste.write_text(json.dumps(manifeste, indent=2))
    for source, nom in (
        (RACINE / ".env", "workspace.env"),
        (RACINE / "gateway/.env", "gateway.env"),
        (RACINE / "gateway/docker-compose.yml", "docker-compose.yml"),
        (RACINE / "gateway/config.yaml", "gateway-config.yaml"),
        (RACINE / "gateway/neo4j-memory.yml", "neo4j-memory.yml"),
    ):
        if source.exists():
            if source.is_symlink():
                raise ValueError("Lien symbolique refusé dans la sauvegarde.")
            shutil.copyfile(source, dossier / nom)
            (dossier / nom).chmod(0o600)
    valeurs = dotenv_values(RACINE / ".env")
    manifeste["memoire"] = exporter_memoire(dossier, valeurs.get("NEO4J_MEMORY_PASSWORD"))
    etat_console = (
        Path(
            os.environ.get("PLATFORM_STATE_DIR")
            or valeurs.get("PLATFORM_STATE_DIR")
            or str(Path.home() / ".local/state/ambicrafted")
        )
        .expanduser()
        .absolute()
    )
    manifeste["console"] = copier_console(etat_console, dossier)
    base = (
        Path(
            os.environ.get("SRE_CHECKPOINT_DB")
            or valeurs.get("SRE_CHECKPOINT_DB")
            or str(Path.home() / ".local/state/sre-agent/graphe.sqlite")
        )
        .expanduser()
        .resolve()
    )
    if base.exists():
        with sqlite3.connect(base.as_uri() + "?mode=ro", uri=True) as entree:
            sortie = sqlite3.connect(dossier / "graphe.sqlite")
            try:
                entree.backup(sortie)
            finally:
                sortie.close()
        entree.close()
    with (dossier / "postgres.dump").open("wb") as fichier:
        subprocess.run(
            [
                "docker",
                "exec",
                "litellm-db",
                "pg_dump",
                "-U",
                "litellm",
                "-d",
                "litellm",
                "-Fc",
            ],
            stdout=fichier,
            stderr=subprocess.PIPE,
            check=True,
            timeout=120,
        )
    # SQLite's backup API captures Grafana consistently, including its WAL.
    image = next(
        line.split("image:", 1)[1].strip()
        for line in (RACINE / "gateway/docker-compose.yml").read_text().splitlines()
        if "image:" in line
    )
    programme = (
        "import sqlite3,os; "
        "a=sqlite3.connect('file:/var/lib/grafana/grafana.db?mode=ro',uri=True); "
        "b=sqlite3.connect('/backup/grafana.sqlite'); a.backup(b); b.close(); a.close(); "
        f"os.chown('/backup/grafana.sqlite',{os.getuid()},{os.getgid()}); "
        "os.chmod('/backup/grafana.sqlite',0o600)"
    )
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--user",
            "0",
            "--volumes-from",
            "grafana:ro",
            "-v",
            f"{dossier}:/backup",
            "--entrypoint",
            "python",
            image,
            "-c",
            programme,
        ],
        check=True,
        capture_output=True,
        timeout=90,
    )
    with httpx.Client(timeout=120, trust_env=False) as client:
        response = client.get("http://127.0.0.1:6333/aliases")
        response.raise_for_status()
        aliases = response.json()["result"]["aliases"]
        manifeste["qdrant_aliases"] = aliases
        collections = client.get("http://127.0.0.1:6333/collections").json()["result"][
            "collections"
        ]
        alias = (
            os.environ.get("QDRANT_COLLECTION")
            or valeurs.get("QDRANT_COLLECTION")
            or "runbooks-current"
        )
        actives = {a["collection_name"] for a in aliases if a["alias_name"] == alias}
        if not actives and any(c["name"] == "runbooks" for c in collections):
            actives.add("runbooks")
        manifeste["qdrant_snapshots"] = []
        for collection in sorted(actives):
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", collection):
                raise ValueError("Nom de collection inattendu.")
            response = client.post(
                f"http://127.0.0.1:6333/collections/{collection}/snapshots"
            )
            response.raise_for_status()
            nom = response.json()["result"]["name"]
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", nom):
                raise ValueError("Nom de snapshot inattendu.")
            with client.stream(
                "GET", f"http://127.0.0.1:6333/collections/{collection}/snapshots/{nom}"
            ) as flux:
                flux.raise_for_status()
                with (dossier / nom).open("wb") as fichier:
                    for bloc in flux.iter_bytes():
                        fichier.write(bloc)
            # Only delete the temporary server-side snapshot created by this call.
            response = client.delete(
                f"http://127.0.0.1:6333/collections/{collection}/snapshots/{nom}"
            )
            response.raise_for_status()
            manifeste["qdrant_snapshots"].append(
                {"collection": collection, "fichier": nom}
            )
    manifeste["complet"] = True
    fichier_manifeste.write_text(json.dumps(manifeste, indent=2))
    return dossier


def purger(jours: int) -> int:
    if jours < 1:
        raise ValueError("Rétention minimale : un jour.")
    if not DESTINATION.exists():
        return 0
    seuil = datetime.now(UTC) - timedelta(days=jours)
    total = 0
    for dossier in DESTINATION.iterdir():
        if dossier.is_symlink() or not re.fullmatch(r"\d{8}T\d{6}Z", dossier.name):
            continue
        manifeste = dossier / "manifest.json"
        if not manifeste.is_file() or manifeste.is_symlink():
            continue
        infos = json.loads(manifeste.read_text())
        if (
            infos.get("type") != "platform-backup-v1"
            or dossier.stat().st_uid != os.getuid()
        ):
            continue
        if datetime.fromisoformat(infos["date"]) < seuil:
            shutil.rmtree(dossier)
            total += 1
    return total


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--purger", action="store_true")
    analyseur.add_argument("--avant", type=int, default=14)
    options = analyseur.parse_args()
    try:
        resultat = (
            {"sauvegardes_purgees": purger(options.avant)}
            if options.purger
            else {"dossier": str(sauvegarder())}
        )
        print(json.dumps(resultat))
        return 0
    except Exception as erreur:  # noqa: BLE001 -- Keep secrets out of operator diagnostics.
        print(
            json.dumps(
                {
                    "erreur": type(erreur).__name__,
                    "message": "Sauvegarde interrompue ; une sauvegarde incomplète ne doit pas être restaurée.",
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
