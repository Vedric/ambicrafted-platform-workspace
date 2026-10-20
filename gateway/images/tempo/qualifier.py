"""Qualify a Tempo binary upgrade with disposable synthetic traces and storage.

Requires Linux Docker and the control API's locked httpx dependency. No live
state, credentials, published ports or external container network is used.
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import subprocess
import time
from pathlib import Path

import httpx

HELPER = (
    "qdrant/qdrant:v1.19.2@sha256:b7b0444c4c351c970b98e90a6f89c2ee4287c65b44e52b4cb503fa5b2aa927ad"
)


def docker(*args):
    return subprocess.check_output(
        ["docker", *args], text=True, stderr=subprocess.PIPE, timeout=120
    ).strip()


def qualify(old_image, new_image, output):
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    prefix = "tempo-qualification-" + secrets.token_hex(5)
    subnet = f"10.234.{secrets.randbelow(254) + 1}"
    network, volume = prefix + "-network", prefix + "-storage"
    containers, resources = [], []
    result = {
        "passed": False,
        "scope": "synthetic OTLP, persisted upgrade and restart",
        "checks": {},
    }
    checks = result["checks"]

    def identifier(image):
        value = docker("image", "ls", "--no-trunc", "--format", "{{.ID}}", image)
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", value):
            raise ValueError("A unique local image is required")
        return value

    old_image, new_image = identifier(old_image), identifier(new_image)
    result["images"] = {"old": old_image, "new": new_image}
    configuration = output / "tempo.yaml"
    configuration.write_text("""server:
  http_listen_port: 3200
usage_report:
  reporting_enabled: false
distributor:
  receivers:
    otlp:
      protocols:
        http:
          endpoint: 0.0.0.0:4318
storage:
  trace:
    backend: local
    local:
      path: /var/tempo/blocks
    wal:
      path: /var/tempo/wal
""")
    configuration.chmod(0o644)

    def start(image, phase):
        name = prefix + "-" + phase
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
            "--memory",
            "1g",
            "--cpus",
            "2",
            "--pids-limit",
            "256",
            "--tmpfs",
            "/tmp:mode=1777,noexec,nosuid,size=128m",
            "--mount",
            f"type=volume,source={volume},target=/var/tempo",
            "--mount",
            f"type=bind,source={configuration},target=/etc/tempo.yaml,readonly",
            image,
            "-config.file=/etc/tempo.yaml",
        )
        containers.append(name)
        return name, address

    with httpx.Client(timeout=5, trust_env=False) as client:

        def wait(address, path, expected=None):
            until = time.monotonic() + 90
            while time.monotonic() < until:
                try:
                    response = client.get(f"http://{address}:3200" + path)
                    if response.status_code == 200 and (
                        expected is None or expected in response.text
                    ):
                        return response
                except httpx.HTTPError:
                    pass
                time.sleep(0.5)
            raise TimeoutError("Synthetic Tempo readiness/query deadline exceeded")

        def submit(address, label):
            trace, span, now = secrets.token_hex(16), secrets.token_hex(8), time.time_ns()
            payload = {
                "resourceSpans": [
                    {
                        "resource": {
                            "attributes": [
                                {
                                    "key": "service.name",
                                    "value": {"stringValue": "synthetic-security"},
                                }
                            ]
                        },
                        "scopeSpans": [
                            {
                                "scope": {"name": "qualification"},
                                "spans": [
                                    {
                                        "traceId": trace,
                                        "spanId": span,
                                        "name": label,
                                        "kind": 1,
                                        "startTimeUnixNano": str(now - 10_000_000),
                                        "endTimeUnixNano": str(now),
                                        "status": {"code": 1},
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
            response = client.post(f"http://{address}:4318/v1/traces", json=payload)
            response.raise_for_status()
            wait(address, "/api/traces/" + trace, label)
            return trace

        try:
            docker("network", "create", "--internal", "--subnet", subnet + ".0/24", network)
            resources.append(("network", network))
            docker("volume", "create", volume)
            resources.append(("volume", volume))
            helper = prefix + "-owner"
            containers.append(helper)
            docker(
                "run",
                "--name",
                helper,
                "--network",
                "none",
                "--user",
                "0",
                "--cap-drop",
                "ALL",
                "--cap-add",
                "CHOWN",
                "--cap-add",
                "DAC_OVERRIDE",
                "--security-opt",
                "no-new-privileges:true",
                "--entrypoint",
                "/bin/chown",
                "--mount",
                f"type=volume,source={volume},target=/synthetic",
                HELPER,
                "10001:10001",
                "/synthetic",
            )
            old, address = start(old_image, "old")
            wait(address, "/ready")
            before = submit(address, "synthetic.before-upgrade")
            checks["baseline_otlp_query"] = True
            docker("stop", "--time", "30", old)
            candidate, address = start(new_image, "candidate")
            wait(address, "/ready")
            wait(address, "/api/traces/" + before, "synthetic.before-upgrade")
            checks["existing_volume_upgrade"] = True
            after = submit(address, "synthetic.after-upgrade")
            checks["candidate_otlp_query"] = True
            invalid = client.post(
                f"http://{address}:4318/v1/traces",
                content=b"{",
                headers={"Content-Type": "application/json"},
            )
            if invalid.status_code != 400:
                raise ValueError("Malformed OTLP payload was not rejected")
            checks["malformed_otlp_rejected"] = True
            docker("restart", "--time", "30", candidate)
            wait(address, "/ready")
            wait(address, "/api/traces/" + before, "synthetic.before-upgrade")
            wait(address, "/api/traces/" + after, "synthetic.after-upgrade")
            checks["both_traces_persist_after_restart"] = True
            metrics = client.get(f"http://{address}:3200/metrics")
            metrics.raise_for_status()
            if "tempo_" not in metrics.text:
                raise ValueError("Tempo metrics missing")
            checks["metrics"] = True
            result["passed"] = True
        except Exception as error:  # noqa: BLE001 -- payloads never appear in diagnostics.
            result["error_type"] = type(error).__name__
        finally:
            failures = []
            for name in reversed(containers):
                try:
                    logs = subprocess.run(
                        ["docker", "logs", name],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        timeout=15,
                        check=False,
                    )
                    (output / (name + ".log")).write_text(logs.stdout)
                    docker("rm", "-f", name)
                except OSError, subprocess.SubprocessError:
                    failures.append(name)
            for kind, name in reversed(resources):
                try:
                    docker(kind, "rm", name)
                except OSError, subprocess.SubprocessError:
                    failures.append(name)
            result["cleanup_failures"] = failures
            result["passed"] = result["passed"] and not failures
            (output / "qualification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    return result["passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-image", required=True)
    parser.add_argument("--new-image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(not qualify(args.old_image, args.new_image, args.output.resolve()))
