# /// script
# requires-python = ">=3.14"
# dependencies = ["httpx==0.28.1"]
# ///
"""Vérifie une sauvegarde dans des conteneurs jetables, sans toucher aux services actifs."""

from __future__ import annotations

import argparse
import json
import re
import secrets
import socket
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
from memoire_sauvegarde import restore_check as verifier_memoire
from sauvegarder import publier_sqlite, sqlite_prive, verifier_dossier_prive

RACINE = Path(__file__).resolve().parents[1]


def verifier_console(dossier: Path, description: dict | None) -> dict:
    """Restore only to disposable files; never reconnect restored authentication state."""
    resultat = {
        "console_presente": False,
        "analyses_console": 0,
        "checkpoints_console": 0,
    }
    if description is not None and not isinstance(description, dict):
        raise TypeError("Description de console invalide.")
    if description is None or description.get("presente") is False:
        if (dossier / "console").exists() or (dossier / "console").is_symlink():
            raise ValueError("La console sauvegardée est absente du manifeste.")
        return resultat
    if (
        description.get("presente") is not True
        or description.get("sessions_exclues") is not True
        or description.get("fichier") != "console/console.sqlite"
        or description.get("atomicite_multi_bases") is not False
        or description.get("coherence") != "sqlite_individuelle"
        or type(description.get("analyses")) is not int
        or type(description.get("sans_checkpoint")) is not int
        or not isinstance(description.get("checkpoints"), list)
    ):
        raise ValueError("Manifeste de console invalide.")
    verifier_dossier_prive(dossier)
    verifier_dossier_prive(dossier / "console")
    with tempfile.TemporaryDirectory(prefix="platform-console-restore-") as temporaire:
        cible = Path(temporaire)
        with sqlite_prive(dossier / "console/console.sqlite") as entree:
            if any(
                entree.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                for table in ("sessions", "tickets")
            ):
                raise ValueError(
                    "La sauvegarde contient des sessions ou tickets d’authentification."
                )
            identifiants = {r[0] for r in entree.execute("SELECT id FROM analyses")}
            if (
                any(
                    not isinstance(i, str) or not re.fullmatch(r"[0-9a-f]{32}", i)
                    for i in identifiants
                )
                or len(identifiants) != description["analyses"]
            ):
                raise ValueError("Inventaire des analyses incohérent.")
            publier_sqlite(entree, cible / "console.sqlite")
        vus = set()
        for checkpoint in description["checkpoints"]:
            if not isinstance(checkpoint, dict):
                raise TypeError("Description de checkpoint invalide.")
            identifiant = checkpoint.get("analyse_id")
            if (
                not isinstance(identifiant, str)
                or not re.fullmatch(r"[0-9a-f]{32}", identifiant)
                or identifiant not in identifiants
                or identifiant in vus
                or checkpoint.get("fichier") != f"console/analyses/{identifiant}/graphe.sqlite"
            ):
                raise ValueError("Identifiant de checkpoint invalide.")
            verifier_dossier_prive(dossier / "console/analyses")
            with sqlite_prive(dossier / checkpoint["fichier"]) as entree:
                publier_sqlite(entree, cible / (identifiant + ".sqlite"))
            vus.add(identifiant)
        if len(identifiants) - len(vus) != description["sans_checkpoint"]:
            raise ValueError("Inventaire des checkpoints incohérent.")
    resultat.update(
        console_presente=True,
        analyses_console=len(identifiants),
        checkpoints_console=len(vus),
        sessions_console=0,
        tickets_console=0,
        sqlite_console=True,
        atomicite_multi_bases=False,
    )
    return resultat


def commande(*args, **kwargs):
    return subprocess.run(
        list(args),
        check=True,
        capture_output=True,
        timeout=120,
        **kwargs,
    )


def verifier(dossier: Path) -> dict:
    manifeste = json.loads((dossier / "manifest.json").read_text())
    if manifeste.get("type") != "platform-backup-v1" or not manifeste.get("complet"):
        raise ValueError("Sauvegarde incomplète.")
    images = {}
    service = ""
    for ligne in (RACINE / "gateway/docker-compose.yml").read_text().splitlines():
        if ligne.startswith("  ") and not ligne.startswith("   ") and ligne.endswith(":"):
            service = ligne.strip().rstrip(":")
        if ligne.strip().startswith("image:"):
            images[service] = ligne.split("image:", 1)[1].strip()
    prefixe = "validationplatform-restore-" + secrets.token_hex(5)
    postgres, qdrant = prefixe + "-pg", prefixe + "-qdrant"
    conteneurs = []
    resultat = verifier_console(dossier, manifeste.get("console"))
    with socket.socket() as sonde:
        sonde.bind(("127.0.0.1", 0))
        port = sonde.getsockname()[1]
    try:
        with tempfile.TemporaryDirectory(prefix="platform-restore-") as temporaire:
            env = Path(temporaire) / "postgres.env"
            env.write_text(
                "POSTGRES_USER=litellm\nPOSTGRES_DB=litellm\nPOSTGRES_PASSWORD="
                + secrets.token_hex(24)
                + "\n"
            )
            env.chmod(0o600)
            commande(
                "docker",
                "run",
                "-d",
                "--name",
                postgres,
                "--network",
                "none",
                "--tmpfs",
                "/var/lib/postgresql/data",
                "--env-file",
                str(env),
                images["postgres"],
            )
            conteneurs.append(postgres)
        for _ in range(60):
            status = subprocess.run(
                [
                    "docker",
                    "exec",
                    postgres,
                    "pg_isready",
                    "-h",
                    "127.0.0.1",
                    "-U",
                    "litellm",
                    "-d",
                    "litellm",
                ],
                capture_output=True,
                timeout=5,
                check=False,
            )
            if status.returncode == 0:
                break
            time.sleep(1)
        with (dossier / "postgres.dump").open("rb") as fichier:
            commande(
                "docker",
                "exec",
                "-i",
                postgres,
                "pg_restore",
                "-U",
                "litellm",
                "-d",
                "litellm",
                "--no-owner",
                "--no-privileges",
                "--exit-on-error",
                stdin=fichier,
            )
        nombre = commande(
            "docker",
            "exec",
            postgres,
            "psql",
            "-U",
            "litellm",
            "-d",
            "litellm",
            "-Atc",
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'",
        ).stdout
        resultat["tables_postgres"] = int(nombre)
        if resultat["tables_postgres"] < 1:
            raise ValueError("Restauration PostgreSQL vide.")
        commande(
            "docker",
            "run",
            "-d",
            "--name",
            qdrant,
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--tmpfs",
            "/qdrant/storage:rw,uid=65532,gid=65532,mode=0700",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=128m",
            "-e",
            "QDRANT__STORAGE__SNAPSHOTS_PATH=/qdrant/storage/snapshots",
            "-e",
            "QDRANT__TELEMETRY_DISABLED=true",
            "-p",
            f"127.0.0.1:{port}:6333",
            images["qdrant"],
        )
        conteneurs.append(qdrant)
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", timeout=120, trust_env=False
        ) as client:
            for _ in range(60):
                try:
                    if client.get("/readyz").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError("Le Qdrant jetable ne devient pas disponible.")
            for i, snapshot in enumerate(manifeste["qdrant_snapshots"]):
                fichier = dossier / snapshot["fichier"]
                if fichier.resolve().parent != dossier.resolve():
                    raise ValueError("Chemin de snapshot invalide.")
                with fichier.open("rb") as entree:
                    response = client.post(
                        f"/collections/restore-{i}/snapshots/upload?priority=snapshot",
                        files={
                            "snapshot": (
                                fichier.name,
                                entree,
                                "application/octet-stream",
                            )
                        },
                    )
                    response.raise_for_status()
                response = client.get(f"/collections/restore-{i}")
                response.raise_for_status()
                resultat[f"points_qdrant_{i}"] = response.json()["result"]["points_count"]
        for nom in ("grafana.sqlite", "graphe.sqlite"):
            if (dossier / nom).exists():
                connexion = sqlite3.connect((dossier / nom).as_uri() + "?mode=ro", uri=True)
                try:
                    resultat[nom] = (
                        connexion.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                    )
                    if not resultat[nom]:
                        raise ValueError("Sauvegarde SQLite incohérente.")
                finally:
                    connexion.close()
        memory_config = RACINE / "gateway/neo4j-memory.yml"
        memory_image = (
            next(
                (
                    line.split("image:", 1)[1].strip()
                    for line in memory_config.read_text().splitlines()
                    if line.strip().startswith("image:")
                ),
                "",
            )
            if memory_config.exists()
            else ""
        )
        resultat.update(verifier_memoire(dossier, manifeste.get("memoire"), memory_image))
        return resultat
    finally:
        for conteneur in reversed(conteneurs):
            commande("docker", "rm", "-fv", conteneur)


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("dossier", type=Path)
    options = analyseur.parse_args()
    try:
        print(json.dumps(verifier(options.dossier), indent=2))
        return 0
    except Exception as erreur:  # noqa: BLE001 -- Keep secrets out of operator diagnostics.
        print(
            json.dumps(
                {
                    "erreur": type(erreur).__name__,
                    "message": "Test de restauration interrompu ; détails sensibles masqués.",
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
