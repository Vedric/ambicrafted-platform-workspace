"""Exercise the actual Grafana loader with deliberately corrupted public plugins.

Only uniquely named disposable containers and an internal network are used.
No live data or credentials are read, and no port is published.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path


def docker(*args):
    return subprocess.check_output(
        ["docker", *args], text=True, stderr=subprocess.PIPE, timeout=120
    ).strip()


def qualify(image, output):
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    suffix = secrets.token_hex(5)
    network = "grafana-signature-refusal-" + suffix
    prefix = "grafana-signature-refusal-" + suffix
    subnet = f"10.232.{secrets.randbelow(254) + 1}"
    address = subnet + ".10"
    password = secrets.token_urlsafe(32)
    authorization = "Basic " + base64.b64encode(("admin:" + password).encode()).decode()
    http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    containers = []
    network_created = False
    result = {
        "image": image,
        "scope": "disposable-synthetic",
        "checks": {},
        "ok": False,
    }

    def request(path):
        req = urllib.request.Request(
            f"http://{address}:3000" + path, headers={"Authorization": authorization}
        )
        with http.open(req, timeout=3) as response:
            return json.loads(response.read(4_000_000))

    try:
        with tempfile.TemporaryDirectory(prefix=prefix) as temporary:
            root = Path(temporary)
            root.chmod(0o755)
            credentials = root / "synthetic.env"
            descriptor = os.open(
                credentials, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
            with os.fdopen(descriptor, "w") as stream:
                stream.write("GF_SECURITY_ADMIN_PASSWORD=" + password + "\n")
                stream.write("GF_ANALYTICS_REPORTING_ENABLED=false\n")
                stream.write("GF_ANALYTICS_CHECK_FOR_UPDATES=false\n")
                stream.write("GF_PLUGINS_PUBLIC_KEY_RETRIEVAL_DISABLED=true\n")
            source_container = docker("create", "--name", prefix + "-extract", image)
            containers.append(source_container)
            pristine = root / "pristine"
            docker(
                "cp",
                source_container
                + ":/usr/share/grafana/data/plugins-bundled/prometheus",
                str(pristine),
            )
            docker("rm", source_container)
            containers.remove(source_container)
            docker(
                "network", "create", "--internal", "--subnet", subnet + ".0/24", network
            )
            network_created = True
            for index, mutation in enumerate(
                [
                    "valid",
                    "binary",
                    "missing-file",
                    "extra-file",
                    "manifest-bytes",
                    "foreign-key-id",
                    "unsigned",
                    "root-url",
                ]
            ):
                plugin = root / mutation
                shutil.copytree(pristine, plugin)
                metadata = json.loads((plugin / "plugin.json").read_text())
                if mutation == "binary":
                    (plugin / (metadata["executable"] + "_linux_amd64")).write_bytes(
                        b"corrupted executable"
                    )
                elif mutation == "missing-file":
                    (plugin / "module.js").unlink()
                elif mutation == "extra-file":
                    (plugin / "unapproved.txt").write_text("synthetic unsigned file")
                elif mutation == "manifest-bytes":
                    manifest = plugin / "MANIFEST.txt"
                    manifest.write_bytes(manifest.read_bytes() + b"\n")
                elif mutation == "foreign-key-id":
                    manifest = plugin / "MANIFEST.txt"
                    before = manifest.read_bytes()
                    after = before.replace(b"f5fdd4382c05e115", b"0000000000000000")
                    if before == after:
                        raise ValueError(
                            "Foreign-key fixture did not modify the manifest"
                        )
                    manifest.write_bytes(after)
                elif mutation == "unsigned":
                    (plugin / "MANIFEST.txt").unlink()
                extra = [
                    "-v",
                    str(plugin)
                    + ":/usr/share/grafana/data/plugins-bundled/prometheus:ro",
                ]
                if mutation == "root-url":
                    extra += [
                        "-e",
                        "GF_SERVER_ROOT_URL=https://unapproved.example.invalid/",
                    ]
                identifier = docker(
                    "run",
                    "-d",
                    "--name",
                    prefix + "-" + str(index),
                    "--network",
                    network,
                    "--ip",
                    address,
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges:true",
                    "--memory",
                    "1g",
                    "--cpus",
                    "2",
                    "--env-file",
                    str(credentials),
                    "--read-only",
                    "--tmpfs",
                    "/var/lib/grafana:uid=472,gid=0,size=128m",
                    "--tmpfs",
                    "/var/log/grafana:uid=472,gid=0,size=32m",
                    "--tmpfs",
                    "/tmp:mode=1777,size=64m",
                    *extra,
                    image,
                )
                containers.append(identifier)
                deadline = time.monotonic() + 90
                while True:
                    try:
                        if request("/api/health").get("database") == "ok":
                            break
                    except OSError:
                        pass
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Synthetic Grafana failed to become ready")
                    time.sleep(0.5)
                installed = {item["id"]: item for item in request("/api/plugins")}
                if mutation == "valid":
                    assert installed["prometheus"]["signature"] == "valid"
                    assert installed["prometheus"]["signatureType"] == "private"
                else:
                    assert "prometheus" not in installed, (
                        "Forbidden plugin was registered by the real loader"
                    )
                if mutation != "root-url":
                    assert installed["tempo"]["signature"] == "valid", (
                        "Unmodified plugin was affected"
                    )
                else:
                    assert "tempo" not in installed, "Root URL restriction was bypassed"
                log = docker("logs", identifier).replace(password, "[redacted]")
                (output / (mutation + ".log")).write_text(log)
                if mutation != "valid":
                    assert "signature" in log.lower(), (
                        "No signature refusal was recorded"
                    )
                result["checks"][mutation] = {
                    "healthy_core": True,
                    "prometheus_loaded": "prometheus" in installed,
                    "tempo_loaded": "tempo" in installed,
                }
                docker("rm", "-f", identifier)
                containers.remove(identifier)
            result["ok"] = True
    finally:
        failures = []
        for identifier in reversed(containers):
            try:
                docker("rm", "-f", identifier)
            except (OSError, subprocess.SubprocessError):
                failures.append(identifier)
        if network_created:
            try:
                docker("network", "rm", network)
            except (OSError, subprocess.SubprocessError):
                failures.append(network)
        result["cleanup_failures"] = failures
        result["ok"] = result["ok"] and not failures
        (output / "qualification.json").write_text(json.dumps(result, indent=2) + "\n")
        print(
            json.dumps({"ok": result["ok"], "completed_checks": list(result["checks"])})
        )
    if not result["ok"]:
        raise RuntimeError("Signature refusal qualification failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    qualify(args.image, args.output.resolve())
