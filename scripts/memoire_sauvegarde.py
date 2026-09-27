"""Bounded logical Neo4j backup; restore only into a disposable authenticated container."""

import hashlib
import json
import os
import re
import secrets
import socket
import stat
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from uuid import UUID

import httpx

MAX_BYTES = 128 * 1024 * 1024
SNAPSHOT = """MATCH (n:AmbicraftedNote)
WITH collect(properties(n)) AS notes
OPTIONAL MATCH (a:AmbicraftedNote)-[:RELATED_TO]->(b:AmbicraftedNote)
WITH notes, collect(CASE WHEN a IS NULL THEN null ELSE {from:a.id,to:b.id} END) AS links
RETURN {notes:notes, links:links}"""


def query(client, statement, parameters=None):
    with client.stream(
        "POST",
        "/db/neo4j/tx/commit",
        json={"statements": [{"statement": statement, "parameters": parameters or {}}]},
    ) as response:
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_bytes(chunk_size=8192):
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                raise ValueError("Memory snapshot exceeds the backup limit")
    result = json.loads(data)
    if result.get("errors"):
        raise ValueError("Memory transaction failed")
    return result["results"][0]["data"]


def validate(data):
    if not isinstance(data, dict) or set(data) != {"notes", "links"}:
        raise ValueError("Invalid memory snapshot")
    if (
        not isinstance(data["notes"], list)
        or len(data["notes"]) > 5000
        or not isinstance(data["links"], list)
        or len(data["links"]) > 75000
    ):
        raise ValueError("Invalid memory inventory")
    notes = {}
    for note in data["notes"]:
        limits = {
            "id": 36,
            "scope": 64,
            "titre": 120,
            "contenu": 4000,
            "source": 500,
            "type": 10,
            "cree_le": 40,
            "maj_le": 40,
        }
        if (
            not isinstance(note, dict)
            or set(note) != set(limits)
            or any(
                not isinstance(note[k], str) or not 1 <= len(note[k]) <= limit
                for k, limit in limits.items()
            )
        ):
            raise ValueError("Invalid memory note")
        if (
            str(UUID(note["id"])) != note["id"]
            or note["id"] in notes
            or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", note["scope"])
            or note["type"] not in {"fact", "decision", "question", "preference"}
        ):
            raise ValueError("Invalid memory note identity")
        if any(datetime.fromisoformat(note[key]).tzinfo is None for key in ("cree_le", "maj_le")):
            raise ValueError("Invalid memory date")
        notes[note["id"]] = note
    links = set()
    for link in data["links"]:
        if (
            not isinstance(link, dict)
            or set(link) != {"from", "to"}
            or any(not isinstance(link[k], str) or link[k] not in notes for k in ("from", "to"))
        ):
            raise ValueError("Invalid memory relationship")
        left, right = sorted((link["from"], link["to"]))
        if left == right or notes[left]["scope"] != notes[right]["scope"] or (left, right) in links:
            raise ValueError("Invalid or cross-scope relationship")
        links.add((left, right))
    return {
        "notes": [notes[key] for key in sorted(notes)],
        "links": [{"from": left, "to": right} for left, right in sorted(links)],
    }


def export(destination: Path, password: str | None) -> dict:
    if not password:
        return {"presente": False}
    with httpx.Client(
        base_url="http://127.0.0.1:47474",
        auth=("neo4j", password),
        trust_env=False,
        follow_redirects=False,
        timeout=30,
    ) as client:
        data = validate(query(client, SNAPSHOT)[0]["row"][0])
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True).encode()
    fd = os.open(
        destination / "memoire.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(fd, "wb") as output:
        output.write(encoded)
    return {
        "presente": True,
        "fichier": "memoire.json",
        "notes": len(data["notes"]),
        "liens": len(data["links"]),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "coherence": "logical-read-committed",
    }


def restore_check(directory: Path, description: dict | None, image: str) -> dict:
    if not description or description.get("presente") is False:
        if (directory / "memoire.json").exists() or (directory / "memoire.json").is_symlink():
            raise ValueError("Memory file absent from manifest")
        return {"memoire_presente": False}
    if (
        description.get("fichier") != "memoire.json"
        or description.get("coherence") != "logical-read-committed"
    ):
        raise ValueError("Invalid memory manifest")
    fd = os.open(directory / "memoire.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
            or info.st_size > MAX_BYTES
        ):
            raise ValueError("Private memory file required")
        encoded = source.read(MAX_BYTES + 1)
    if len(encoded) > MAX_BYTES or hashlib.sha256(encoded).hexdigest() != description.get("sha256"):
        raise ValueError("Memory checksum mismatch")
    data = validate(json.loads(encoded))
    if len(data["notes"]) != description.get("notes") or len(data["links"]) != description.get(
        "liens"
    ):
        raise ValueError("Memory inventory mismatch")
    name = "validationplatform-memory-restore-" + secrets.token_hex(5)
    password = secrets.token_urlsafe(48)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    try:
        with tempfile.TemporaryDirectory(prefix=name) as temporary:
            env = Path(temporary) / "neo4j.env"
            env.write_text(
                "NEO4J_AUTH=neo4j/"
                + password
                + "\nNEO4J_server_memory_heap_initial__size=256m\nNEO4J_server_memory_heap_max__size=512m\nNEO4J_server_memory_pagecache_size=256m\nNEO4J_server_bolt_listen__address=127.0.0.1:7687\nNEO4J_dbms_usage__report_enabled=false\n"
            )
            env.chmod(0o600)
            subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    name,
                    "--env-file",
                    str(env),
                    "--tmpfs",
                    "/data:uid=7474,gid=7474",
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
                ],
                capture_output=True,
                timeout=120,
                check=True,
            )
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}",
            auth=("neo4j", password),
            trust_env=False,
            follow_redirects=False,
            timeout=30,
        ) as client:
            end = time.monotonic() + 120
            while True:
                try:
                    query(client, "RETURN 1")
                    break
                except httpx.HTTPError, ValueError:
                    if time.monotonic() >= end:
                        raise TimeoutError("Disposable memory did not start") from None
                    time.sleep(1)
            query(
                client,
                "CREATE CONSTRAINT ambicrafted_note_id IF NOT EXISTS FOR (n:AmbicraftedNote) REQUIRE n.id IS UNIQUE",
            )
            for offset in range(0, len(data["notes"]), 100):
                query(
                    client,
                    "UNWIND $notes AS note CREATE (n:AmbicraftedNote) SET n = note",
                    {"notes": data["notes"][offset : offset + 100]},
                )
            for offset in range(0, len(data["links"]), 500):
                query(
                    client,
                    "UNWIND $links AS link MATCH (a:AmbicraftedNote {id:link.from}), (b:AmbicraftedNote {id:link.to}) CREATE (a)-[:RELATED_TO]->(b)",
                    {"links": data["links"][offset : offset + 500]},
                )
            if validate(query(client, SNAPSHOT)[0]["row"][0]) != data:
                raise ValueError("Restored memory differs from snapshot")
        return {
            "memoire_presente": True,
            "notes_memoire": len(data["notes"]),
            "liens_memoire": len(data["links"]),
            "contenu_memoire_verifie": True,
        }
    finally:
        subprocess.run(["docker", "rm", "-fv", name], capture_output=True, timeout=30, check=False)
