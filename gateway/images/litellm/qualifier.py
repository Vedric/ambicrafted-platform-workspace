"""Exercise gateway migration/authentication and logical rollback on synthetic state.

No production credentials, databases or containers are read. Only the local model
endpoint from the reviewed gateway configuration may receive synthetic prompts.
Run with the locked control API environment.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]


def command(*argv, **kwargs):
    return subprocess.run(argv, capture_output=True, check=True, timeout=180, **kwargs)


def available_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def wait_database(name):
    for _ in range(90):
        try:
            command(
                "docker", "exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "litellm"
            )
            return
        except subprocess.CalledProcessError:
            time.sleep(1)
    raise TimeoutError("Synthetic database failed to start")


def wait_gateway(client, master):
    for _ in range(120):
        try:
            if (
                client.get(
                    "/health/readiness", headers={"Authorization": "Bearer " + master}
                ).status_code
                == 200
            ):
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise TimeoutError("Synthetic gateway failed to start")


def check_gateway(client, key, *, inference):
    for headers in ({}, {"Authorization": "Bearer sk-invalid-synthetic"}):
        assert client.get("/v1/models", headers=headers).status_code == 401
    headers = {"Authorization": "Bearer " + key}
    models = client.get("/v1/models", headers=headers)
    models.raise_for_status()
    assert {m["id"] for m in models.json()["data"]} == {"local", "local-embed"}
    denied = client.post(
        "/v1/chat/completions",
        headers=headers,
        json={"model": "smart", "messages": [{"role": "user", "content": "synthetic"}]},
    )
    assert denied.status_code in {400, 401, 403}
    # Exercise inference formats through the same restricted alias key.
    if inference:
        embedding = client.post(
            "/v1/embeddings",
            headers=headers,
            json={"model": "local-embed", "input": "Synthetic gateway qualification"},
            timeout=90,
        )
        embedding.raise_for_status()
        assert len(embedding.json()["data"][0]["embedding"]) > 0
        structured = client.post(
            "/v1/chat/completions",
            headers=headers,
            timeout=90,
            json={
                "model": "local",
                "max_tokens": 128,
                "temperature": 0,
                "reasoning_effort": "none",
                "messages": [
                    {
                        "role": "user",
                        "content": "Return a JSON observation: label synthetic, observations 2.",
                    }
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "gateway_qualification",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string", "enum": ["synthetic"]},
                                "observations": {"type": "integer", "enum": [2]},
                            },
                            "required": ["label", "observations"],
                            "additionalProperties": False,
                        },
                    },
                },
            },
        )
        structured.raise_for_status()
        assert json.loads(structured.json()["choices"][0]["message"]["content"]) == {
            "label": "synthetic",
            "observations": 2,
        }
        with client.stream(
            "POST",
            "/v1/chat/completions",
            headers=headers,
            timeout=90,
            json={
                "model": "local",
                "stream": True,
                "max_tokens": 24,
                "think": False,
                "messages": [
                    {"role": "user", "content": "Reply only with: synthetic check"}
                ],
            },
        ) as stream:
            stream.raise_for_status()
            ended, content = False, False
            for line in stream.iter_lines():
                if line == "data: [DONE]":
                    ended = True
                elif line.startswith("data: "):
                    event = json.loads(line[6:])
                    content |= any(
                        c.get("delta", {}).get("content")
                        for c in event.get("choices", [])
                    )
            assert ended and content


def qualify(old_image, new_image, postgres_image):
    prefix = "validationplatform-gateway-" + secrets.token_hex(6)
    network, volume, rollback_volume = (
        prefix + "-net",
        prefix + "-db",
        prefix + "-rollback",
    )
    db, old, new, rollback_db, rollback = [
        prefix + suffix
        for suffix in ("-postgres", "-old", "-new", "-rollback-db", "-rollback-gateway")
    ]
    port, rollback_port = available_port(), available_port()
    checks = {}
    result = {
        "scope": "synthetic isolated gateway migration and logical rollback",
        "old_image": old_image,
        "new_image": new_image,
        "postgres_image": postgres_image,
        "checks": checks,
    }
    master, password = "sk-" + secrets.token_hex(32), secrets.token_hex(24)
    containers = [db, old, new, rollback_db, rollback]
    volumes = [volume, rollback_volume]
    created_containers, created_volumes = [], []
    network_created = False
    with tempfile.TemporaryDirectory(prefix=prefix) as temporary:
        directory = Path(temporary)
        environment = directory / "credentials"
        environment.touch(mode=0o600)
        environment.write_text(
            f"LITELLM_MASTER_KEY={master}\nPOSTGRES_PASSWORD={password}\n"
            "POSTGRES_USER=litellm\nPOSTGRES_DB=litellm\n"
            f"DATABASE_URL=postgresql://litellm:{password}@postgres:5432/litellm\n"
            "ANTHROPIC_API_KEY=unused-synthetic-no-cloud-call\n"
            "LITELLM_TELEMETRY=False\n"
        )

        def start_db(name, disk):
            command(
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "--network",
                network,
                "--network-alias",
                "postgres",
                "--env-file",
                str(environment),
                "--mount",
                f"type=volume,source={disk},target=/var/lib/postgresql/data",
                "--security-opt",
                "no-new-privileges:true",
                postgres_image,
            )
            created_containers.append(name)
            wait_database(name)

        def start_gateway(name, image, exposed_port):
            command(
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "--network",
                network,
                "--env-file",
                str(environment),
                "--security-opt",
                "no-new-privileges:true",
                "--mount",
                f"type=bind,source={ROOT / 'gateway/config.yaml'},target=/app/config.yaml,readonly",
                "-p",
                f"127.0.0.1:{exposed_port}:4000",
                image,
                "--config",
                "/app/config.yaml",
                "--port",
                "4000",
            )
            created_containers.append(name)

        try:
            command("docker", "network", "create", network)
            network_created = True
            for disk in volumes:
                command("docker", "volume", "create", disk)
                created_volumes.append(disk)
            start_db(db, volume)
            start_gateway(old, old_image, port)
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port}", timeout=10, trust_env=False
            ) as client:
                wait_gateway(client, master)
                response = client.post(
                    "/key/generate",
                    headers={"Authorization": "Bearer " + master},
                    json={
                        "key_alias": "qualification-local-only",
                        "models": ["local", "local-embed"],
                    },
                )
                response.raise_for_status()
                key = response.json()["key"]
                check_gateway(client, key, inference=False)
                checks["old_key_and_auth"] = True
                backup = command(
                    "docker", "exec", db, "pg_dump", "-U", "litellm", "-Fc", "litellm"
                ).stdout
                assert len(backup) > 1000
                command("docker", "stop", old)
                start_gateway(new, new_image, port)
                wait_gateway(client, master)
                check_gateway(client, key, inference=True)
                checks["migrated_key_auth_streaming_embeddings"] = True
                checks["structured_output_schema"] = True
                command("docker", "restart", new)
                wait_gateway(client, master)
                check_gateway(client, key, inference=False)
                checks["key_survives_restart"] = True
            command("docker", "stop", new)
            command("docker", "stop", db)
            # A pre-upgrade dump is restored into a separate volume. We never
            # run the older gateway against a database migrated by the new one.
            command("docker", "network", "disconnect", network, db)
            start_db(rollback_db, rollback_volume)
            command(
                "docker",
                "exec",
                "-i",
                rollback_db,
                "pg_restore",
                "-U",
                "litellm",
                "-d",
                "litellm",
                "--no-owner",
                "--no-privileges",
                "--exit-on-error",
                input=backup,
            )
            start_gateway(rollback, old_image, rollback_port)
            with httpx.Client(
                base_url=f"http://127.0.0.1:{rollback_port}",
                timeout=10,
                trust_env=False,
            ) as client:
                wait_gateway(client, master)
                check_gateway(client, key, inference=False)
                checks["logical_rollback_preserves_key_and_auth"] = True
        except (
            AssertionError,
            OSError,
            ValueError,
            KeyError,
            httpx.HTTPError,
            subprocess.SubprocessError,
        ) as error:
            # Neither SDK messages nor container output are safe to publish.
            result["error_type"] = type(error).__name__
        finally:
            cleanup = True
            for name in reversed(created_containers):
                assert name in containers
                try:
                    command("docker", "rm", "-f", name)
                except subprocess.SubprocessError:
                    cleanup = False
            for disk in created_volumes:
                try:
                    command("docker", "volume", "rm", disk)
                except subprocess.SubprocessError:
                    cleanup = False
            if network_created:
                try:
                    command("docker", "network", "rm", network)
                except subprocess.SubprocessError:
                    cleanup = False
            checks["isolated_resources_removed"] = cleanup
    result["passed"] = (
        len(checks) == 6 and all(checks.values()) and "error_type" not in result
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-image", required=True)
    parser.add_argument("--new-image", required=True)
    parser.add_argument("--postgres-image", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    fd = os.open(
        args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(fd, "w") as report:
        result = qualify(args.old_image, args.new_image, args.postgres_image)
        json.dump(result, report, indent=2)
    print(json.dumps(result))
    return not result["passed"]


if __name__ == "__main__":
    raise SystemExit(main())
