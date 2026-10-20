"""Nonempty synthetic recovery exercise; never reads or replaces the operator's databases.

Run with the control API's locked environment. Models are not called. An optional
Neo4j check restores two synthetic notes into a disposable authenticated container.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from exporter_sauvegarde import chiffrer, dechiffrer
from inventaire_sauvegarde import copier_sources, inventaire
from memoire_sauvegarde import restore_check, validate
from sauvegarder import copier_console
from tester_restauration import verifier_console

MISSION = "0123456789abcdef0123456789abcdef"
AUTH_MARKER = "SYNTHETIC-AUTH-MUST-NOT-BE-EXPORTED"
CHECKPOINT = {
    "statut": "abandon",
    "message": "Synthetic recovery exercise; no action executed.",
}


def composants():
    # The sibling scripts/plateforme.py must not shadow the installed control API package.
    original = sys.path[:]
    script_dir = Path(__file__).resolve().parent
    try:
        sys.path[:] = [
            entry for entry in sys.path if Path(entry).resolve() != script_dir
        ]
        from plateforme.conversations import Conversations
        from plateforme.depot import Depot

        from sre_agent.graphe import compiler

        return Conversations, Depot, compiler
    finally:
        sys.path[:] = original


def preparer(dossier: Path) -> tuple[Path, dict]:
    Conversations, Depot, compiler = composants()
    dossier.mkdir(mode=0o700)
    state, backup = dossier / "state", dossier / "backup"
    backup.mkdir(mode=0o700)
    depot = Depot(state)
    depot.creer(
        MISSION, "Synthetic PostgreSQL incident", "graphe", {}, "synthetic-drill"
    )
    depot.changer(MISSION, "termine", rapport=CHECKPOINT)
    conversations = Conversations(depot)
    thread = conversations.creer("Synthetic recovery discussion")["id"]
    attachment = conversations.ajouter_piece(
        thread,
        "synthetic.csv",
        {
            "kind": "text",
            "text": "service,status\nsynthetic,ok\n",
            "truncated": False,
        },
    )
    conversations.enregistrer_tour(
        thread,
        "synthetic-operation",
        "What evidence do we have?",
        {
            "texte": "A synthetic CSV; verify the source before acting.",
            "usage": {"tokens": 12},
        },
        "synthetic-request-fingerprint",
    )
    with depot.connexion() as connection:
        for table in ("sessions", "tickets"):
            connection.execute(
                f"INSERT INTO {table} VALUES(?,?)", (AUTH_MARKER, 9999999999)
            )
    graph_path = state / "analyses" / MISSION / "graphe.sqlite"
    graph = compiler(str(graph_path))
    try:
        graph.update_state(
            {"configurable": {"thread_id": MISSION}}, CHECKPOINT, as_node="abandon"
        )
    finally:
        graph.checkpointer.conn.close()
    corpus = dossier / "runbooks"
    corpus.mkdir(mode=0o700)
    (corpus / "synthetic.md").write_text(
        "# Synthetic incident\n\nInspect evidence before acting.\n"
    )
    memory = validate(
        {
            "notes": [
                {
                    "id": f"00000000-0000-4000-8000-{number:012d}",
                    "scope": "synthetic",
                    "titre": "Recovery evidence",
                    "contenu": "Synthetic source verified.",
                    "source": "synthetic.md",
                    "type": "fact",
                    "cree_le": "2026-10-20T00:00:00+00:00",
                    "maj_le": "2026-10-20T00:00:00+00:00",
                }
                for number in (1, 2)
            ],
            "links": [
                {
                    "from": "00000000-0000-4000-8000-000000000001",
                    "to": "00000000-0000-4000-8000-000000000002",
                }
            ],
        }
    )
    encoded = json.dumps(memory, sort_keys=True).encode()
    (backup / "memoire.json").write_bytes(encoded)
    (backup / "memoire.json").chmod(0o600)
    manifest = {
        "type": "platform-backup-v1",
        "complet": True,
        "synthetique": True,
        "console": copier_console(state, backup),
        "sources": copier_sources(corpus, [], backup),
        "memoire": {
            "presente": True,
            "fichier": "memoire.json",
            "notes": 2,
            "liens": 1,
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "coherence": "logical-read-committed",
        },
    }
    manifest["integrite"] = inventaire(backup)
    (backup / "manifest.json").write_text(json.dumps(manifest))
    (backup / "manifest.json").chmod(0o600)
    return backup, {
        "conversation": thread,
        "piece": attachment["id"],
        "manifest": manifest,
    }


def exercer(dossier: Path, *, image_neo4j: str | None = None) -> dict:
    Conversations, Depot, compiler = composants()
    backup, expected = preparer(dossier / "fixture")
    identity, recipients = dossier / "identity.txt", dossier / "recipients.txt"
    keygen = shutil.which("age-keygen")
    if not keygen:
        raise ValueError("age-keygen is required")
    subprocess.run(
        [keygen, "-o", str(identity)], capture_output=True, timeout=10, check=True
    )
    identity.chmod(0o600)
    recipients.write_bytes(
        subprocess.run(
            [keygen, "-y", str(identity)],
            capture_output=True,
            timeout=10,
            check=True,
        ).stdout
    )
    recipients.chmod(0o600)
    archive, restored = dossier / "synthetic.tar.age", dossier / "restored"
    chiffrer(backup, recipients, archive)
    dechiffrer(archive, identity, restored)
    manifest = expected["manifest"]
    result = verifier_console(restored, manifest["console"])
    recovered = Depot(restored / "console")
    if recovered.obtenir(MISSION)["rapport"] != CHECKPOINT:
        raise ValueError("Mission report differs after recovery")
    thread = Conversations(recovered).obtenir(expected["conversation"])
    if thread["total_messages"] != 2 or thread["pieces"][0]["id"] != expected["piece"]:
        raise ValueError("Conversation or attachment missing after recovery")
    if [message["content"] for message in thread["messages"]] != [
        "What evidence do we have?",
        "A synthetic CSV; verify the source before acting.",
    ]:
        raise ValueError("Conversation content differs after recovery")
    context = Conversations(recovered).contexte(
        expected["conversation"], "Read the source", [expected["piece"]]
    )
    if "service,status\nsynthetic,ok\n" not in context[-1]["content"][-1]["text"]:
        raise ValueError("Extracted attachment cannot be read through the application")
    graph = compiler(str(restored / "console/analyses" / MISSION / "graphe.sqlite"))
    try:
        values = graph.get_state({"configurable": {"thread_id": MISSION}}).values
        if any(values.get(key) != value for key, value in CHECKPOINT.items()):
            raise ValueError("LangGraph checkpoint differs after recovery")
    finally:
        graph.checkpointer.conn.close()
    for path in backup.rglob("*"):
        if path.is_file() and AUTH_MARKER.encode() in path.read_bytes():
            raise ValueError("Authentication material leaked into the backup")
    memory = validate(json.loads((restored / "memoire.json").read_text()))
    result.update(
        {
            "mission_relue": True,
            "checkpoint_langgraph_relu": True,
            "conversation_relue": True,
            "piece_jointe_relue": True,
            "chiffrement_age_aller_retour": True,
            "notes_memoire": len(memory["notes"]),
            "liens_memoire": len(memory["links"]),
            "neo4j_restaure": False,
            "services_actifs_modifies": False,
            "synthetique": True,
        }
    )
    if image_neo4j:
        result.update(restore_check(restored, manifest["memoire"], image_neo4j))
        result["neo4j_restaure"] = True
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--neo4j-image", help="Pinned local image for a disposable graph restore"
    )
    args = parser.parse_args()
    os.umask(0o077)
    try:
        with tempfile.TemporaryDirectory(
            prefix="platform-synthetic-recovery-"
        ) as temporary:
            print(
                json.dumps(
                    exercer(Path(temporary), image_neo4j=args.neo4j_image), indent=2
                )
            )
        return 0
    except Exception as error:  # noqa: BLE001 -- never disclose private payloads or keys.
        print(
            json.dumps(
                {
                    "erreur": type(error).__name__,
                    "message": "Synthetic recovery exercise failed.",
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
