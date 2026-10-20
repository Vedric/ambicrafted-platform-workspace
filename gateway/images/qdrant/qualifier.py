"""Qualify Qdrant upgrades and snapshot rollback using disposable synthetic state.

Requires a local Linux Docker Engine. No live volume, credentials or host port is
used: the host reaches a private internal bridge directly. No container has
external network access.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import subprocess
import time
from contextlib import closing
from pathlib import Path

import httpx

OWNERSHIP_HELPER = "qdrant/qdrant:v1.19.2@sha256:b7b0444c4c351c970b98e90a6f89c2ee4287c65b44e52b4cb503fa5b2aa927ad"


def docker(*args):
    return subprocess.check_output(
        ["docker", *args], text=True, stderr=subprocess.PIPE, timeout=120
    ).strip()


def qualify(old_image, new_image, output):
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    prefix = "qdrant-qualification-" + secrets.token_hex(5)
    subnet = f"10.232.{secrets.randbelow(254) + 1}"
    network = prefix + "-network"
    containers, volumes = [], []
    network_created = False
    checks = {}
    result = {
        "scope": "synthetic migration, persistence, search and snapshot rollback",
        "old_image": old_image,
        "new_image": new_image,
        "checks": checks,
        "passed": False,
    }

    def image_id(image):
        identifier = docker("image", "ls", "--no-trunc", "--format", "{{.ID}}", image)
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", identifier):
            raise ValueError("A single locally available image is required")
        return identifier

    old_image, new_image = image_id(old_image), image_id(new_image)
    result["image_ids"] = {"old": old_image, "new": new_image}
    points = [
        {
            "id": 1,
            "vector": [1.0, 0.0, 0.0],
            "payload": {"team": "alpha", "text": "first"},
        },
        {
            "id": 2,
            "vector": [0.8, 0.6, 0.0],
            "payload": {"team": "alpha", "text": "second"},
        },
        {
            "id": 3,
            "vector": [0.0, 0.0, 1.0],
            "payload": {"team": "beta", "text": "third"},
        },
    ]
    alias = "synthetic-current"
    collection = "synthetic"

    def disk(label):
        name = prefix + "-" + label
        docker("volume", "create", name)
        volumes.append(name)
        return name

    def start(image, volume, label):
        name = prefix + "-" + label
        address = subnet + f".{len(containers) + 10}"
        docker(
            "run",
            "-d",
            "--name",
            name,
            "--network",
            network,
            "--ip",
            address,
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--cpus",
            "2",
            "--memory",
            "1g",
            "--tmpfs",
            "/tmp:mode=1777,noexec,nosuid,size=128m",
            "--mount",
            f"type=volume,source={volume},target=/qdrant/storage",
            "-e",
            "QDRANT__STORAGE__SNAPSHOTS_PATH=/qdrant/storage/snapshots",
            "-e",
            "QDRANT__TELEMETRY_DISABLED=true",
            "-e",
            "QDRANT_INIT_FILE_PATH=/qdrant/storage/.qdrant-initialized",
            image,
        )
        containers.append(name)
        client = httpx.Client(
            base_url=f"http://{address}:6333", timeout=30, trust_env=False
        )
        last_status = None
        for _ in range(60):
            try:
                last_status = client.get("/readyz", timeout=2).status_code
                if last_status == 200:
                    return name, client
            except httpx.HTTPError as error:
                last_status = type(error).__name__
            time.sleep(1)
        client.close()
        result["readiness_failure"] = {"phase": label, "status": last_status}
        raise RuntimeError("Disposable Qdrant did not become ready")

    def request(client, method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()["result"]

    def snapshot(client, target, label):
        item = request(client, "POST", f"/collections/{target}/snapshots")
        response = client.get(f"/collections/{target}/snapshots/{item['name']}")
        response.raise_for_status()
        data = response.content
        assert 0 < len(data) < 16 * 1024**2
        (output / (label + ".snapshot")).write_bytes(data)
        return data

    def restore(client, data, target):
        return request(
            client,
            "POST",
            f"/collections/{target}/snapshots/upload",
            params={"priority": "snapshot"},
            files={
                "snapshot": ("synthetic.snapshot", data, "application/octet-stream")
            },
        )

    def verify(client, expected, target=alias):
        actual = request(
            client,
            "POST",
            f"/collections/{target}/points/scroll",
            json={"limit": 100, "with_payload": True, "with_vector": True},
        )["points"]
        assert len(actual) == len(expected)
        for got, wanted in zip(
            sorted(actual, key=lambda x: x["id"]),
            sorted(expected, key=lambda x: x["id"]),
            strict=True,
        ):
            assert got["id"] == wanted["id"] and got["payload"] == wanted["payload"]
            assert len(got["vector"]) == len(wanted["vector"])
            assert all(
                abs(a - b) < 1e-6
                for a, b in zip(got["vector"], wanted["vector"], strict=True)
            )
        found = request(
            client,
            "POST",
            f"/collections/{target}/points/query",
            json={
                "query": [1.0, 0.0, 0.0],
                "limit": 10,
                "with_payload": True,
                "filter": {"must": [{"key": "team", "match": {"value": "alpha"}}]},
            },
        )["points"]
        assert [p["id"] for p in found] == [1, 2]
        assert found[0]["score"] > found[1]["score"]
        config = request(client, "GET", f"/collections/{target}")
        assert config["points_count"] == len(expected)
        assert config["payload_schema"]["team"]["data_type"] == "keyword"
        return {"points": len(actual), "filtered_ranked_ids": [p["id"] for p in found]}

    def normalize_owner(volume):
        # Dedicated *synthetic* volume only. Real upgrades must stop writers,
        # preserve a backup and migrate only their dedicated storage explicitly.
        helper = prefix + "-ownership-" + secrets.token_hex(3)
        try:
            docker(
                "run",
                "--name",
                helper,
                "--network",
                "none",
                "--user",
                "0",
                "--security-opt",
                "no-new-privileges:true",
                "--cap-drop",
                "ALL",
                "--cap-add",
                "CHOWN",
                "--cap-add",
                "DAC_OVERRIDE",
                "--mount",
                f"type=volume,source={volume},target=/synthetic",
                "--entrypoint",
                "/bin/chown",
                OWNERSHIP_HELPER,
                "-R",
                "65532:65532",
                "/synthetic",
            )
        finally:
            docker("rm", "-f", helper)

    try:
        docker("network", "create", "--internal", "--subnet", subnet + ".0/24", network)
        network_created = True
        storage = disk("storage")
        baseline, client = start(old_image, storage, "old")
        with closing(client):
            assert client.get("/").json()["version"] == "1.19.1"
            request(
                client,
                "PUT",
                f"/collections/{collection}",
                json={
                    "vectors": {"size": 3, "distance": "Cosine"},
                    "on_disk_payload": True,
                },
            )
            request(
                client,
                "PUT",
                f"/collections/{collection}/index",
                params={"wait": "true"},
                json={"field_name": "team", "field_schema": "keyword"},
            )
            request(
                client,
                "PUT",
                f"/collections/{collection}/points",
                params={"wait": "true"},
                json={"points": points},
            )
            request(
                client,
                "POST",
                "/collections/aliases",
                json={
                    "actions": [
                        {
                            "create_alias": {
                                "collection_name": collection,
                                "alias_name": alias,
                            }
                        }
                    ],
                },
            )
            checks["baseline_search_and_payload_index"] = verify(client, points)
            before = snapshot(client, collection, "before-upgrade")
            docker("restart", baseline)
            for _ in range(60):
                try:
                    if client.get("/readyz", timeout=2).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            else:
                raise TimeoutError("Baseline restart failed")
            checks["baseline_restart"] = verify(client, points)
        docker("stop", baseline)
        normalize_owner(storage)
        checks["explicit_synthetic_ownership_migration"] = True
        upgraded, client = start(new_image, storage, "upgraded")
        with closing(client):
            assert client.get("/").json()["version"] == "1.19.2"
            checks["upgraded_existing_storage"] = verify(client, points)
            assert request(client, "GET", "/aliases")["aliases"] == [
                {"alias_name": alias, "collection_name": collection}
            ]
            docker("exec", upgraded, "/qdrant/healthcheck")
            dashboard = client.get("/dashboard/")
            assert dashboard.status_code == 200 and '<div id="root"' in dashboard.text
            checks["healthcheck_and_dashboard_http"] = True
            changed = [
                *points[:2],
                {
                    "id": 4,
                    "vector": [0.0, 1.0, 0.0],
                    "payload": {"team": "beta", "text": "after upgrade"},
                },
            ]
            request(
                client,
                "PUT",
                f"/collections/{alias}/points",
                params={"wait": "true"},
                json={"points": [changed[-1]]},
            )
            request(
                client,
                "POST",
                f"/collections/{alias}/points/delete",
                params={"wait": "true"},
                json={"points": [3]},
            )
            checks["upgraded_write_delete"] = verify(client, changed)
            docker("restart", upgraded)
            for _ in range(60):
                try:
                    if client.get("/readyz", timeout=2).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            else:
                raise TimeoutError("Upgraded restart failed")
            checks["upgraded_restart"] = verify(client, changed)
            after = snapshot(client, collection, "after-upgrade")
        restored_disk = disk("restored")
        normalize_owner(restored_disk)
        _, client = start(new_image, restored_disk, "restored")
        with closing(client):
            restore(client, before, "before")
            restore(client, after, "after")
            checks["new_restores_old_snapshot"] = verify(client, points, "before")
            checks["new_restores_new_snapshot"] = verify(client, changed, "after")
            # Collection snapshots do not restore aliases: rebuild them deliberately.
            assert request(client, "GET", "/aliases")["aliases"] == []
            request(
                client,
                "POST",
                "/collections/aliases",
                json={
                    "actions": [
                        {
                            "create_alias": {
                                "collection_name": "after",
                                "alias_name": alias,
                            }
                        }
                    ],
                },
            )
            checks["restored_alias_recreated"] = verify(client, changed)
        rollback_disk = disk("rollback")
        _, client = start(old_image, rollback_disk, "rollback")
        with closing(client):
            assert client.get("/").json()["version"] == "1.19.1"
            restore(client, before, collection)
            checks["old_restores_pre_upgrade_snapshot"] = verify(
                client, points, collection
            )
        checks["snapshot_sha256"] = {
            "before": hashlib.sha256(before).hexdigest(),
            "after": hashlib.sha256(after).hexdigest(),
        }
        result["passed"] = True
    except Exception as error:  # noqa: BLE001 -- no container or HTTP payload in diagnostics.
        result["error_type"] = type(error).__name__
    finally:
        failures = []
        for name in reversed(containers):
            try:
                log = subprocess.run(
                    ["docker", "logs", name],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=15,
                    text=True,
                    check=False,
                ).stdout
                (output / (name + ".log")).write_text(log)
            except (OSError, subprocess.SubprocessError):
                pass
            try:
                docker("rm", "-f", name)
            except (OSError, subprocess.SubprocessError):
                failures.append(name)
        for name in reversed(volumes):
            try:
                docker("volume", "rm", name)
            except (OSError, subprocess.SubprocessError):
                failures.append(name)
        if network_created:
            try:
                docker("network", "rm", network)
            except (OSError, subprocess.SubprocessError):
                failures.append(network)
        result["cleanup_failures"] = failures
        result["passed"] = result["passed"] and not failures
        (output / "qualification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    return result["passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-image", required=True)
    parser.add_argument("--new-image", required=True)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    raise SystemExit(
        not qualify(arguments.old_image, arguments.new_image, arguments.output)
    )
