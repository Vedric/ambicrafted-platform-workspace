"""Exercise gateway migration/authentication and logical rollback on synthetic state.

No production credentials, databases or containers are read. Only the local model
endpoint from the reviewed gateway configuration may receive synthetic prompts.
Run with the locked control API environment.
"""

from __future__ import annotations

import argparse
import base64
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


def check_gateway(client, key, *, inference, progress=None, generation=True):
    progress = progress if progress is not None else {}
    progress["phase"] = "authentication"
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
        progress["phase"] = "embedding"
        embedding = client.post(
            "/v1/embeddings",
            headers=headers,
            json={"model": "local-embed", "input": "Synthetic gateway qualification"},
            timeout=90,
        )
        embedding.raise_for_status()
        assert len(embedding.json()["data"][0]["embedding"]) > 0
        progress["embedding_completed"] = True
        if not generation:
            progress["phase"] = "embedding_only_complete"
            return
        progress["phase"] = "structured_response"
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
        progress["structured_response_completed"] = True
        progress["phase"] = "streaming"
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
        progress["streaming_completed"] = True
    progress["phase"] = "complete"


def check_trace_delivery(client, key, tempo_port):
    """Send actual gateway requests and retrieve their exported Tempo spans."""

    def spans(value):
        if isinstance(value, dict):
            if "spanId" in value and "traceId" in value:
                yield value
            for item in value.values():
                yield from spans(item)
        elif isinstance(value, list):
            for item in value:
                yield from spans(item)

    def identifier(value):
        if len(value) in {16, 32} and all(c in "0123456789abcdef" for c in value):
            return value
        return base64.b64decode(value, validate=True).hex()

    with httpx.Client(
        base_url=f"http://127.0.0.1:{tempo_port}", timeout=10, trust_env=False
    ) as tempo:
        for state, expected in [
            ("vendor=synthetic", "vendor=synthetic"),
            # Internal OWS is valid HTTP; trailing whitespace is refused by
            # the client before it can exercise the gateway's 8,192 limit.
            ("foo=1" + " " * 8182 + ",bar=2", ""),
        ]:
            trace_id, parent_id = secrets.token_hex(16), secrets.token_hex(8)
            response = client.post(
                "/v1/embeddings",
                headers={
                    "Authorization": "Bearer " + key,
                    "traceparent": f"00-{trace_id}-{parent_id}-01",
                    "tracestate": state,
                },
                json={
                    "model": "local-embed",
                    "input": "Synthetic tracing qualification",
                },
                timeout=90,
            )
            response.raise_for_status()
            assert response.json()["data"][0]["embedding"]
            delivered = []
            for _ in range(60):
                retrieved = tempo.get("/api/traces/" + trace_id)
                if retrieved.status_code == 200:
                    delivered = list(spans(retrieved.json()))
                    if delivered:
                        break
                time.sleep(1)
            assert delivered, "Gateway trace did not reach the isolated Tempo"
            assert all(identifier(span["traceId"]) == trace_id for span in delivered)
            roots = [
                span
                for span in delivered
                if identifier(span.get("parentSpanId", "")) == parent_id
            ]
            assert roots, "Exported span lost the caller's parent"
            assert all(span.get("traceState", "") == expected for span in roots)


def acceptance(checks, *, generation_requested, tempo_requested, error_present=False):
    required = {
        "old_key_and_auth",
        "key_survives_restart",
        "logical_rollback_preserves_key_and_auth",
        "isolated_resources_removed",
    }
    if generation_requested:
        required.update(
            {"migrated_key_auth_streaming_embeddings", "structured_output_schema"}
        )
    else:
        required.add("migrated_key_auth_embeddings")
    if tempo_requested:
        required.add("real_otlp_delivery_parent_and_tracestate_boundary")
    profile_passed = (
        set(checks) == required
        and all(checks[name] is True for name in required)
        and not error_present
    )
    return {
        "profile_passed": profile_passed,
        "passed": profile_passed and generation_requested,
    }


def qualify(
    old_image, new_image, postgres_image, tempo_image=None, embeddings_only=False
):
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
    tempo, tempo_port, tempo_volume = (
        prefix + "-tempo",
        available_port(),
        prefix + "-traces",
    )
    checks = {}
    inference_progress = {}
    result = {
        "scope": "synthetic isolated gateway migration and logical rollback",
        "old_image": old_image,
        "new_image": new_image,
        "postgres_image": postgres_image,
        "checks": checks,
        "inference_progress": inference_progress,
        "generation_requested": not embeddings_only,
    }
    master, password = "sk-" + secrets.token_hex(32), secrets.token_hex(24)
    containers = [db, old, new, rollback_db, rollback]
    volumes = [volume, rollback_volume]
    if tempo_image:
        containers.append(tempo)
        volumes.append(tempo_volume)
        result["tempo_image"] = tempo_image
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
            + (
                "OTEL_EXPORTER=otlp_http\nOTEL_ENDPOINT=http://tempo:4318/v1/traces\n"
                "OTEL_SERVICE_NAME=synthetic-gateway-qualification\n"
                "OTEL_BSP_SCHEDULE_DELAY=200\n"
                if tempo_image
                else ""
            )
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
            if tempo_image:
                tempo_config = directory / "tempo.yaml"
                tempo_config.write_text(
                    "server:\n  http_listen_port: 3200\n"
                    "usage_report:\n  reporting_enabled: false\n"
                    "distributor:\n  receivers:\n    otlp:\n      protocols:\n"
                    "        http:\n          endpoint: 0.0.0.0:4318\n"
                    "storage:\n  trace:\n    backend: local\n    local:\n"
                    "      path: /var/tempo/blocks\n    wal:\n      path: /var/tempo/wal\n"
                )
                tempo_config.chmod(0o644)
                command(
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    tempo,
                    "--network",
                    network,
                    "--network-alias",
                    "tempo",
                    "--read-only",
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges:true",
                    "--memory",
                    "1g",
                    "--cpus",
                    "2",
                    "--pids-limit",
                    "256",
                    "--tmpfs",
                    "/tmp:mode=1777,noexec,nosuid,size=128m",
                    "--mount",
                    f"type=volume,source={tempo_volume},target=/var/tempo",
                    "--mount",
                    f"type=bind,source={tempo_config},target=/etc/tempo.yaml,readonly",
                    "-p",
                    f"127.0.0.1:{tempo_port}:3200",
                    tempo_image,
                    "-config.file=/etc/tempo.yaml",
                )
                created_containers.append(tempo)
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
                check_gateway(
                    client,
                    key,
                    inference=True,
                    progress=inference_progress,
                    generation=not embeddings_only,
                )
                if embeddings_only:
                    checks["migrated_key_auth_embeddings"] = True
                else:
                    checks["migrated_key_auth_streaming_embeddings"] = True
                    checks["structured_output_schema"] = True
                if tempo_image:
                    check_trace_delivery(client, key, tempo_port)
                    checks["real_otlp_delivery_parent_and_tracestate_boundary"] = True
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
    # A limited diagnostic never satisfies the full migration/inference gate.
    result.update(
        acceptance(
            checks,
            generation_requested=not embeddings_only,
            tempo_requested=bool(tempo_image),
            error_present="error_type" in result,
        )
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-image", required=True)
    parser.add_argument("--new-image", required=True)
    parser.add_argument("--postgres-image", required=True)
    parser.add_argument(
        "--tempo-image", help="Optional isolated real OTLP trace verification"
    )
    parser.add_argument(
        "--embeddings-only",
        action="store_true",
        help="Limited diagnostic: do not call generation; the full passed gate remains false",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    fd = os.open(
        args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(fd, "w") as report:
        result = qualify(
            args.old_image,
            args.new_image,
            args.postgres_image,
            args.tempo_image,
            args.embeddings_only,
        )
        json.dump(result, report, indent=2)
    print(json.dumps(result))
    return not result["profile_passed"]


if __name__ == "__main__":
    raise SystemExit(main())
