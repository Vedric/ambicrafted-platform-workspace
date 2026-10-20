"""Qualify an isolated Neo4j patch upgrade and logical rollback using synthetic data only.

Run using the control API's locked environment. Never reads production credentials,
uses production ports/volumes, or replaces an existing service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from memoire_sauvegarde import SNAPSHOT, query, restore_check, validate


def command(*arguments):
    return subprocess.run(list(arguments), capture_output=True, check=True, timeout=120)


def start(name: str, image: str, volume: str, environment: Path, password: str):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    command(
        "docker",
        "run",
        "-d",
        "--name",
        name,
        "--env-file",
        str(environment),
        "--volume",
        volume + ":/data",
        "--tmpfs",
        "/logs:uid=7474,gid=7474",
        "--memory",
        "2g",
        "--cpus",
        "2",
        "--pids-limit",
        "256",
        "--security-opt",
        "no-new-privileges:true",
        "-p",
        f"127.0.0.1:{port}:7474",
        image,
    )
    client = httpx.Client(
        base_url=f"http://127.0.0.1:{port}",
        auth=("neo4j", password),
        trust_env=False,
        follow_redirects=False,
        timeout=10,
    )
    deadline = time.monotonic() + 120
    try:
        while True:
            try:
                query(client, "RETURN 1")
                return client
            except (httpx.HTTPError, ValueError):
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        "Synthetic Neo4j instance did not start"
                    ) from None
                time.sleep(1)
    except BaseException:
        client.close()
        raise


def authentication(client):
    body = {"statements": [{"statement": "RETURN 1"}]}
    for credentials in (None, ("neo4j", "wrong-synthetic-password")):
        response = client.post("/db/neo4j/tx/commit", json=body, auth=credentials)
        if response.status_code != 401:
            raise ValueError("Anonymous or incorrect authentication was accepted")


def qualify(old_image: str, new_image: str) -> dict:
    token = "validationplatform-neo4j-" + secrets.token_hex(6)
    names = [token + suffix for suffix in ("-old", "-new", "-restart")]
    volume = token + "-data"
    password = secrets.token_urlsafe(48)
    os.umask(0o077)
    command(
        "docker", "volume", "create", "--label", "ambicrafted.synthetic=true", volume
    )
    try:
        with tempfile.TemporaryDirectory(prefix=token) as temporary:
            folder = Path(temporary)
            environment = folder / "neo4j.env"
            environment.write_text(
                "NEO4J_AUTH=neo4j/" + password + "\n"
                "NEO4J_server_memory_heap_initial__size=256m\n"
                "NEO4J_server_memory_heap_max__size=512m\n"
                "NEO4J_server_memory_pagecache_size=256m\n"
                "NEO4J_server_bolt_listen__address=127.0.0.1:7687\n"
                "NEO4J_dbms_usage__report_enabled=false\n"
                "NEO4J_db_transaction_timeout=10s\n"
            )
            environment.chmod(0o600)
            note = {
                "id": "00000000-0000-4000-8000-000000000001",
                "scope": "synthetic",
                "titre": "Mémoire synthétique",
                "contenu": "Evidence before action — vérification.",
                "source": "Synthetic upgrade fixture",
                "type": "fact",
                "cree_le": "2026-10-20T00:00:00+00:00",
                "maj_le": "2026-10-20T00:00:00+00:00",
            }
            with closing(start(names[0], old_image, volume, environment, password)) as client:
                authentication(client)
                query(
                    client,
                    "CREATE CONSTRAINT ambicrafted_note_id IF NOT EXISTS FOR (n:AmbicraftedNote) REQUIRE n.id IS UNIQUE",
                )
                query(
                    client,
                    "CREATE INDEX ambicrafted_note_scope IF NOT EXISTS FOR (n:AmbicraftedNote) ON (n.scope)",
                )
                query(
                    client, "CREATE (n:AmbicraftedNote) SET n = $note", {"note": note}
                )
                second = {
                    **note,
                    "id": "00000000-0000-4000-8000-000000000002",
                    "type": "decision",
                }
                query(
                    client, "CREATE (n:AmbicraftedNote) SET n = $note", {"note": second}
                )
                query(
                    client,
                    "MATCH (a:AmbicraftedNote {id:$a}),(b:AmbicraftedNote {id:$b}) CREATE (a)-[:RELATED_TO]->(b)",
                    {"a": note["id"], "b": second["id"]},
                )
                original = validate(query(client, SNAPSHOT)[0]["row"][0])
            encoded = json.dumps(original, sort_keys=True).encode()
            (folder / "memoire.json").write_bytes(encoded)
            description = {
                "presente": True,
                "fichier": "memoire.json",
                "notes": 2,
                "liens": 1,
                "sha256": hashlib.sha256(encoded).hexdigest(),
                "coherence": "logical-read-committed",
            }
            command("docker", "stop", "-t", "30", names[0])
            command("docker", "rm", "-fv", names[0])
            with closing(start(names[1], new_image, volume, environment, password)) as client:
                authentication(client)
                version = query(
                    client, "CALL dbms.components() YIELD versions RETURN versions[0]"
                )[0]["row"][0]
                if version != "5.26.32":
                    raise ValueError("Unexpected candidate database version")
                if validate(query(client, SNAPSHOT)[0]["row"][0]) != original:
                    raise ValueError("Persistent graph differs after upgrade")
                if (
                    query(
                        client,
                        "MATCH (n:AmbicraftedNote {scope:$scope}) RETURN count(n)",
                        {"scope": "another-scope"},
                    )[0]["row"][0]
                    != 0
                ):
                    raise ValueError("Scoped query returned unrelated notes")
                try:
                    query(
                        client, "CREATE (n:AmbicraftedNote) SET n=$note", {"note": note}
                    )
                except ValueError:
                    pass
                else:
                    raise ValueError("Uniqueness constraint was lost")
                query(
                    client,
                    "MATCH (n:AmbicraftedNote {id:$id}) SET n.contenu=$text",
                    {"id": note["id"], "text": "Synthetic update survives a restart."},
                )
                updated = validate(query(client, SNAPSHOT)[0]["row"][0])
            command("docker", "stop", "-t", "30", names[1])
            command("docker", "rm", "-fv", names[1])
            with closing(start(names[2], new_image, volume, environment, password)) as client:
                authentication(client)
                if validate(query(client, SNAPSHOT)[0]["row"][0]) != updated:
                    raise ValueError("Candidate write did not survive restart")
            command("docker", "stop", "-t", "30", names[2])
            command("docker", "rm", "-fv", names[2])
            restored = restore_check(folder, description, new_image)
            rollback = restore_check(folder, description, old_image)
            return {
                "synthetic": True,
                "old_image": old_image,
                "new_image": new_image,
                "version": version,
                "persistent_upgrade": True,
                "restart_persistence": True,
                "authentication_rejections": True,
                "scope_filter": True,
                "uniqueness_constraint": True,
                "backup_notes": 2,
                "backup_links": 1,
                "candidate_logical_restore": restored["contenu_memoire_verifie"],
                "pre_upgrade_backup_rollback": rollback["contenu_memoire_verifie"],
                "live_services_modified": False,
            }
    finally:
        for name in reversed(names):
            subprocess.run(
                ["docker", "rm", "-fv", name],
                capture_output=True,
                timeout=30,
                check=False,
            )
        subprocess.run(
            ["docker", "volume", "rm", volume],
            capture_output=True,
            timeout=30,
            check=False,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-image", required=True)
    parser.add_argument("--new-image", required=True)
    options = parser.parse_args()
    try:
        print(json.dumps(qualify(options.old_image, options.new_image), indent=2))
        return 0
    except Exception as error:  # noqa: BLE001 -- no credentials/container logs in diagnostics.
        print(
            json.dumps(
                {
                    "error": type(error).__name__,
                    "message": "Synthetic Neo4j qualification failed.",
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
