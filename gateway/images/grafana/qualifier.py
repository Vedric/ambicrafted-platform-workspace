"""Qualify a Grafana derivative with disposable state and synthetic telemetry.

No live volumes, secrets or external network are used. The Linux host reaches
the internal Docker bridge directly; no container port is published. Only
resources created by this process are removed.
"""

import argparse
import base64
import json
import os
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

PROMETHEUS = (
    "prom/prometheus:v3.15.0"
    "@sha256:efd719c99d83b060d9daefdcf00360461adf279f45ef5391f8d111892118753e"
)
TEMPO = (
    "grafana/tempo:3.0.3"
    "@sha256:0296560ac66f8a3600d7fb3014a52c189d4d9c3549ad6ff441bf2409855d68d5"
)
ROOT = Path(__file__).resolve().parents[3]


def docker(*args):
    return subprocess.check_output(
        ["docker", *args], text=True, stderr=subprocess.PIPE, timeout=120
    ).strip()


def qualify(image, output, browser=None):
    suffix = secrets.token_hex(5)
    network = "grafana-qualification-" + suffix
    password = secrets.token_urlsafe(32)
    created = []
    addresses = {}
    subnet = f"10.231.{secrets.randbelow(254) + 1}"
    result = {"image": image, "scope": "isolated-synthetic", "checks": {}, "ok": False}
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    checks = result["checks"]
    http = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def run(name, target, extra, args=()):
        full_name = name + "-qualification-" + suffix
        address = subnet + f".{len(created) + 10}"
        identifier = docker(
            "run",
            "-d",
            "--name",
            full_name,
            "--network",
            network,
            "--ip",
            address,
            "--network-alias",
            name,
            "--security-opt",
            "no-new-privileges:true",
            "--cap-drop",
            "ALL",
            "--cpus",
            "2",
            "--memory",
            "1g",
            *extra,
            target,
            *args,
        )
        created.append((identifier, full_name))
        addresses[identifier] = address
        return identifier

    def port(identifier, number):
        # Internal Docker networks deliberately do not publish host ports. Use
        # the fixture's bridge address on a local Linux Docker Engine instead.
        address = addresses[identifier]
        return f"http://{address}:{number}"

    def request(url, data=None, auth=False):
        headers = {}
        if auth:
            headers["Authorization"] = (
                "Basic " + base64.b64encode(("admin:" + password).encode()).decode()
            )
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            url,
            headers=headers,
            data=json.dumps(data).encode() if data is not None else None,
        )
        with http.open(req, timeout=10) as response:
            body = response.read(8_000_001)
            assert len(body) <= 8_000_000
            return json.loads(body) if body else None

    def ready(url):
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                with http.open(url, timeout=2) as response:
                    if response.status == 200:
                        return
            except OSError:
                pass
            time.sleep(1)
        raise AssertionError("Synthetic service did not become ready")

    network_created = False
    try:
        with tempfile.TemporaryDirectory(prefix="grafana-qualification-") as directory:
            temporary = Path(directory)
            # Containers must traverse the fixture directory; its credential
            # file remains owner-only, is read by Docker, and is never mounted.
            temporary.chmod(0o755)
            tempo_config = temporary / "tempo.yaml"
            tempo_config.write_text(
                "server:\n  http_listen_port: 3200\n"
                "usage_report:\n  reporting_enabled: false\n"
                "distributor:\n  receivers:\n    otlp:\n      protocols:\n"
                "        http:\n          endpoint: 0.0.0.0:4318\n"
                "storage:\n  trace:\n    backend: local\n"
                "    local:\n      path: /tmp/tempo/blocks\n"
                "    wal:\n      path: /tmp/tempo/wal\n"
            )
            prometheus_config = temporary / "prometheus.yaml"
            prometheus_config.write_text(
                "global:\n  scrape_interval: 1s\nscrape_configs:\n"
                "  - job_name: synthetic-prometheus\n    static_configs:\n"
                "      - targets: ['localhost:9090']\n"
            )
            credentials = temporary / "qualification.env"
            descriptor = os.open(
                credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
            with os.fdopen(descriptor, "w") as stream:
                stream.write("GF_SECURITY_ADMIN_PASSWORD=" + password + "\n")
                stream.write(
                    "GF_ANALYTICS_REPORTING_ENABLED=false\n"
                    "GF_ANALYTICS_CHECK_FOR_UPDATES=false\n"
                    "GF_PLUGINS_PREINSTALL_DISABLED=true\n"
                    "GF_PLUGINS_PREINSTALL_AUTO_UPDATE=false\n"
                    "GF_PLUGINS_PUBLIC_KEY_RETRIEVAL_DISABLED=true\n"
                )
            docker(
                "network", "create", "--internal", "--subnet", subnet + ".0/24", network
            )
            network_created = True
            tempo = run(
                "tempo",
                TEMPO,
                [
                    "--tmpfs",
                    "/tmp:mode=1777,size=256m",
                    "-v",
                    str(tempo_config) + ":/etc/tempo.yaml:ro",
                ],
                ["-config.file=/etc/tempo.yaml"],
            )
            run(
                "prometheus",
                PROMETHEUS,
                [
                    "--tmpfs",
                    "/prometheus:uid=65534,gid=65534,size=256m",
                    "-v",
                    str(prometheus_config) + ":/etc/prometheus/prometheus.yml:ro",
                ],
            )
            provisioning = ROOT / "gateway/observability/grafana"
            grafana = run(
                "grafana",
                image,
                [
                    "--env-file",
                    str(credentials),
                    "--tmpfs",
                    "/var/lib/grafana:uid=472,gid=0,size=256m",
                    "--tmpfs",
                    "/var/log/grafana:uid=472,gid=0,size=64m",
                    "-v",
                    str(provisioning / "datasources")
                    + ":/etc/grafana/provisioning/datasources:ro",
                    "-v",
                    str(provisioning / "dashboards")
                    + ":/etc/grafana/provisioning/dashboards:ro",
                    "-v",
                    str(provisioning / "json") + ":/var/lib/grafana/dashboards:ro",
                ],
            )
            base = port(grafana, 3000)
            ready(base + "/api/health")
            ready(port(tempo, 3200) + "/ready")
            checks["health"] = request(base + "/api/health")
            assert checks["health"]["database"] == "ok"
            assert checks["health"]["version"] == "13.2.4+ambicrafted.20261020.r2"
            try:
                request(base + "/api/datasources")
                raise AssertionError("Anonymous datasource access was accepted")
            except urllib.error.HTTPError as error:
                assert error.code == 401
            checks["authentication_required"] = True
            provenance = json.loads(
                Path(__file__).with_name("plugins-provenance.json").read_text()
            )
            expected = dict(provenance["inherited_plugins"])
            expected.update(
                {item["id"]: item["version"] for item in provenance["plugins"]}
            )
            installed = {
                item["id"]: item for item in request(base + "/api/plugins", auth=True)
            }
            signatures = {
                identifier: {
                    "signature": installed[identifier].get("signature"),
                    "signatureType": installed[identifier].get("signatureType"),
                    "signatureOrg": installed[identifier].get("signatureOrg"),
                    "version": installed[identifier].get("info", {}).get("version"),
                }
                for identifier in expected
            }
            assert len(signatures) == 2
            assert all(
                item["signature"] == "valid"
                and item["signatureType"] == "private"
                and item["signatureOrg"] == "Ambicrafted local distribution"
                and item["version"] == expected[identifier]
                for identifier, item in signatures.items()
            ), signatures
            checks["plugin_signatures_and_versions"] = signatures
            assert not set(provenance["removed_unused_plugins"]).intersection(installed)
            checks["unused_plugins_absent"] = len(provenance["removed_unused_plugins"])
            sources = request(base + "/api/datasources", auth=True)
            assert {source["uid"] for source in sources} == {"prometheus", "tempo"}
            checks["datasources"] = sorted(source["uid"] for source in sources)
            dashboards = []
            for filename in sorted((provisioning / "json").glob("*.json")):
                expected_uid = json.loads(filename.read_text())["uid"]
                stored = request(
                    base + "/api/dashboards/uid/" + expected_uid, auth=True
                )
                panels = stored["dashboard"]["panels"]
                assert panels and stored["dashboard"]["uid"] == expected_uid
                dashboards.append(
                    {
                        "uid": expected_uid,
                        "panels": len(panels),
                        "content_panels": sum(
                            panel["type"] != "row" for panel in panels
                        ),
                        "url": stored["meta"]["url"],
                    }
                )
            assert len(dashboards) == 6
            checks["provisioned_dashboards"] = dashboards
            now = time.time_ns()
            trace_id = secrets.token_hex(16)
            payload = {
                "resourceSpans": [
                    {
                        "resource": {
                            "attributes": [
                                {
                                    "key": "service.name",
                                    "value": {
                                        "stringValue": "grafana-qualification-synthetic"
                                    },
                                }
                            ]
                        },
                        "scopeSpans": [
                            {
                                "spans": [
                                    {
                                        "traceId": trace_id,
                                        "spanId": secrets.token_hex(8),
                                        "name": "synthetic-validation",
                                        "startTimeUnixNano": str(now - 10_000_000),
                                        "endTimeUnixNano": str(now),
                                        "kind": 1,
                                    }
                                ]
                            }
                        ],
                    }
                ]
            }
            request(port(tempo, 4318) + "/v1/traces", payload)
            time.sleep(3)
            envelope = {
                "from": str(now // 1_000_000 - 60_000),
                "to": str(now // 1_000_000 + 60_000),
            }
            for name, reference, query in [
                (
                    "prometheus",
                    "prometheus",
                    {
                        "expr": "up",
                        "instant": True,
                        "range": False,
                        "format": "time_series",
                    },
                ),
                ("tempo", "tempo", {"queryType": "traceId", "query": trace_id}),
                (
                    "tempo_traceql",
                    "tempo",
                    {
                        "queryType": "traceql",
                        "query": '{ resource.service.name = "grafana-qualification-synthetic" }',
                    },
                ),
            ]:
                query_request = {
                    **envelope,
                    "queries": [
                        {
                            "refId": "A",
                            "datasource": {"type": reference, "uid": reference},
                            "intervalMs": 1000,
                            "maxDataPoints": 100,
                            **query,
                        }
                    ],
                }
                deadline = time.monotonic() + 30
                while True:
                    data = request(base + "/api/ds/query", query_request, auth=True)
                    item = data["results"]["A"]
                    if name != "tempo_traceql" or trace_id in json.dumps(
                        item.get("frames", [])
                    ):
                        break
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(1)
                (output / (name + "-synthetic-response.json")).write_text(
                    json.dumps(data, indent=2) + "\n"
                )
                item = data["results"]["A"]
                assert item.get("frames") and not item.get("error"), reference
                if reference == "tempo":
                    assert trace_id in json.dumps(item["frames"]), name
                checks[name + "_backend_query"] = {"frames": len(item["frames"])}
            if browser:
                # Synthetic temporary credentials enter via stdin, never argv,
                # shell history, test reports or browser screenshots.
                process = subprocess.run(
                    ["node", str(browser)],
                    input=json.dumps(
                        {
                            "base": base,
                            "password": password,
                            "dashboards": dashboards,
                            "root": str(ROOT),
                            "output": str(output),
                        }
                    ),
                    capture_output=True,
                    text=True,
                    timeout=180,
                    check=False,
                )
                (output / "browser-stderr.log").write_text(
                    process.stderr.replace(password, "[redacted]")
                )
                assert process.returncode == 0, "Browser qualification failed"
                checks["browser"] = json.loads(process.stdout)
            result["ok"] = True
    finally:
        cleanup_failures = []
        for identifier, name in reversed(created):
            try:
                log = subprocess.run(
                    ["docker", "logs", identifier],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=20,
                    check=False,
                ).stdout.replace(password, "[redacted]")
                (output / (name + ".log")).write_text(log)
            except (OSError, subprocess.TimeoutExpired):
                pass
            try:
                removal = subprocess.run(
                    ["docker", "rm", "-f", identifier],
                    capture_output=True,
                    timeout=30,
                    check=False,
                )
                if removal.returncode:
                    cleanup_failures.append(name)
            except (OSError, subprocess.TimeoutExpired):
                cleanup_failures.append(name)
        if network_created:
            try:
                removal = subprocess.run(
                    ["docker", "network", "rm", network],
                    capture_output=True,
                    timeout=30,
                    check=False,
                )
                if removal.returncode:
                    cleanup_failures.append(network)
            except (OSError, subprocess.TimeoutExpired):
                cleanup_failures.append(network)
        result["cleanup_failures"] = cleanup_failures
        result["ok"] = result["ok"] and not cleanup_failures
        (output / "qualification.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({"ok": result["ok"], "completed_checks": list(checks)}))
    if not result["ok"]:
        raise RuntimeError("Grafana qualification or resource cleanup failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--browser", type=Path, help="Optional Playwright qualification script"
    )
    args = parser.parse_args()
    qualify(args.image, args.output.resolve(), args.browser)
