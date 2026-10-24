"""Qualify a Grafana derivative with disposable state and synthetic telemetry.

No live volumes, secrets or external network are used. The Linux host reaches
the internal Docker bridge directly; no container port is published. Only
resources created by this process are removed.
"""

import argparse
import base64
import hashlib
import json
import math
import os
import secrets
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


def synthetic_metrics(started):
    """Generate public fixture samples; never import operator measurements."""
    elapsed = max(1, int(time.monotonic() - started))
    lines = []
    histogram_types = set()

    def sample(name, value, **labels):
        suffix = (
            "{" + ",".join(f'{k}="{v}"' for k, v in labels.items()) + "}"
            if labels
            else ""
        )
        lines.append(f"{name}{suffix} {value}")

    def histogram(name, value, buckets, **labels):
        if name not in histogram_types:
            lines.append(f"# TYPE {name} histogram")
            histogram_types.add(name)
        # Each second adds one identical observation, yielding monotonic buckets.
        for upper in [*buckets, "+Inf"]:
            sample(
                name + "_bucket",
                elapsed if float(upper) >= value else 0,
                **labels,
                le=str(float(upper)) if upper != "+Inf" else "+Inf",
            )
        sample(name + "_count", elapsed, **labels)
        sample(name + "_sum", elapsed * value, **labels)

    now = time.time()
    for metric, value in {
        "snapshot_timestamp_seconds": now,
        "control_api_scrape_success": 1,
        "retained_conversations": 12,
        "retained_documents": 8,
        "retained_messages": 41,
        "inference_busy": 0,
        "queue_depth": 1,
        "queue_capacity": 4,
        "index_points": 256,
        "retained_tokens_entree": 18000,
        "retained_tokens_sortie": 6000,
        "retained_tokens": 24000,
        "retained_cout_usd": 0.08,
        "host_memory_memavailable_bytes": 6000000000,
        "host_memory_memtotal_bytes": 16000000000,
        "host_memory_swaptotal_bytes": 2000000000,
        "host_memory_swapfree_bytes": 1900000000,
        "data_disk_available_bytes": 80000000000,
        "data_disk_size_bytes": 100000000000,
        "data_disk_inodes_available_ratio": 0.9,
        "backup_last_completed_timestamp_seconds": now - 3600,
        "backup_available": 1,
        "host_load1": 1.2,
        "host_cpu_count": 8,
        "gpu_memory_used_bytes": 8000000000,
        "gpu_memory_total_bytes": 16000000000,
        "gpu_utilization_ratio": 0.3,
        "gpu_temperature_celsius": 48,
        "gpu_power_watts": 120,
    }.items():
        sample("ambicrafted_" + metric, value)
    sample("process_resident_memory_bytes", 120000000)
    for name in ["tokens_entree", "tokens_sortie", "tokens", "cout_usd"]:
        sample("ambicrafted_retained_" + name + "_measured_runs", 5)
    for mode, factor in [("idle", 6), ("user", 1), ("system", 1)]:
        sample(
            "ambicrafted_host_cpu_seconds_total", elapsed * factor, mode=mode, cpu="0"
        )
    for service in ["gateway", "ollama", "qdrant", "neo4j", "voice", "mcp"]:
        sample("ambicrafted_service_up", 1, service=service)
        sample("ambicrafted_service_probe_duration_seconds", 0.02, service=service)
    for kind in ["graphe", "operation"]:
        for state, value in [("termine", 5), ("en_attente_humain", 1), ("erreur", 1)]:
            sample("ambicrafted_retained_runs", value, kind=kind, state=state)
    buckets = [0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 60, 120, 300]
    for group in [
        "analyses",
        "conversations",
        "speech_recognition",
        "speech_synthesis",
        "assistant",
        "memory",
        "knowledge",
    ]:
        for outcome, factor in [
            ("success", 20),
            ("server_error", 1),
            ("client_error", 1),
            ("cancelled", 1),
        ]:
            sample(
                "ambicrafted_http_requests_total",
                elapsed * factor,
                group=group,
                outcome=outcome,
            )
        histogram(
            "ambicrafted_http_request_duration_seconds", 0.1, buckets, group=group
        )
    for format_ in ["text", "diagram", "report"]:
        for outcome, factor in [
            ("success", 20),
            ("error", 1),
            ("timeout", 1),
            ("cancelled", 1),
        ]:
            sample(
                "ambicrafted_aura_operations_total",
                elapsed * factor,
                format=format_,
                outcome=outcome,
            )
            histogram(
                "ambicrafted_aura_operation_duration_seconds",
                20 if outcome == "success" else 60,
                buckets,
                format=format_,
                outcome=outcome,
            )
    for mode in ["text", "voice"]:
        histogram("ambicrafted_aura_first_token_seconds", 0.5, buckets, mode=mode)
    for route in ["workspace", "assistant", "guide"]:
        histogram(
            "ambicrafted_browser_web_vital_seconds",
            1.1,
            buckets,
            metric="LCP",
            route=route,
        )
        histogram(
            "ambicrafted_browser_web_vital_seconds",
            0.08,
            buckets,
            metric="INP",
            route=route,
        )
        histogram(
            "ambicrafted_browser_layout_shift_ratio",
            0.01,
            [0, 0.01, 0.05, 0.1, 0.25, 0.5, 1],
            route=route,
        )
    sample(
        "ambicrafted_document_failures_total", elapsed, code="document_review_rejected"
    )
    for outcome in ["queued", "sent", "failed", "dropped"]:
        sample(
            "ambicrafted_trace_spans_total",
            elapsed * (2 if outcome in {"queued", "sent"} else 0),
            outcome=outcome,
        )
    return ("\n".join(lines) + "\n").encode()


def qualify(
    image,
    output,
    browser=None,
    prometheus_image=PROMETHEUS,
    tempo_image=TEMPO,
    dashboard_uids=(),
):
    suffix = secrets.token_hex(5)
    network = "grafana-qualification-" + suffix
    password = secrets.token_urlsafe(32)
    created = []
    addresses = {}
    subnet = f"10.231.{secrets.randbelow(254) + 1}"
    # Hash only the files this process mounts or copies into its fixture. Tests
    # and generators are not executed here and may be worked on concurrently.
    configuration = ROOT / "gateway/observability"
    source_paths = sorted(
        [
            configuration / "alerts.yml",
            configuration / "slo.yml",
            configuration / "tempo.yaml",
            *[
                path
                for path in (configuration / "grafana").rglob("*")
                if path.is_file()
            ],
        ]
    )
    source_hashes = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_paths
        if path.is_file() and "__pycache__" not in path.parts
    }
    result = {
        "image": image,
        "prometheus_image": prometheus_image,
        "tempo_image": tempo_image,
        "scope": "isolated-synthetic",
        "source_sha256": source_hashes,
        "qualifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "browser_sha256": hashlib.sha256(browser.read_bytes()).hexdigest()
        if browser
        else None,
        "checks": {},
        "ok": False,
    }
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    checks = result["checks"]
    http = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def run(name, target, extra, args=()):
        full_name = name + "-qualification-" + suffix
        address = subnet + f".{len(created) + 10}"
        identifier = docker(
            "run",
            "-d",
            "--pull",
            "never",
            "--pids-limit",
            "256",
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
    exporter = None
    exporter_thread = None
    try:
        with tempfile.TemporaryDirectory(prefix="grafana-qualification-") as directory:
            temporary = Path(directory)
            # Containers must traverse the fixture directory; its credential
            # file remains owner-only, is read by Docker, and is never mounted.
            temporary.chmod(0o755)
            tempo_config = temporary / "tempo.yaml"
            # Exercise the actual candidate Tempo configuration and SLO rules.
            tempo_config.write_bytes(
                (ROOT / "gateway/observability/tempo.yaml").read_bytes()
            )
            prometheus_config = temporary / "prometheus.yaml"
            prometheus_config.write_text(
                "global:\n  scrape_interval: 1s\n  evaluation_interval: 15s\n"
                "rule_files: ['/etc/prometheus/alerts.yml', "
                "'/etc/prometheus/slo.yml']\n"
                "scrape_configs:\n"
                "  - job_name: prometheus\n    static_configs:\n"
                "      - targets: ['localhost:9090']\n"
                "  - job_name: tempo\n    static_configs:\n"
                "      - targets: ['tempo:3200']\n"
                "  - job_name: grafana\n    static_configs:\n"
                "      - targets: ['grafana:3000']\n"
                "  - job_name: platform\n    static_configs:\n"
                "      - targets: ['" + subnet + ".1:PORT_PLACEHOLDER']\n"
            )
            # Public synthetic configs must remain readable by non-root
            # containers even when the operator uses a restrictive umask.
            tempo_config.chmod(0o644)
            prometheus_config.chmod(0o644)
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
            started = time.monotonic()

            class FixtureHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path != "/metrics":
                        self.send_error(404)
                        return
                    body = synthetic_metrics(started)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; version=0.0.4")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, *_args):
                    pass

            exporter = ThreadingHTTPServer((subnet + ".1", 0), FixtureHandler)
            exporter_thread = threading.Thread(
                target=exporter.serve_forever, daemon=True
            )
            exporter_thread.start()
            prometheus_config.write_text(
                prometheus_config.read_text().replace(
                    "PORT_PLACEHOLDER", str(exporter.server_port)
                )
            )
            tempo = run(
                "tempo",
                tempo_image,
                [
                    "--tmpfs",
                    "/var/tempo:uid=10001,gid=10001,mode=1777,size=256m",
                    "-v",
                    str(tempo_config) + ":/etc/tempo.yaml:ro",
                ],
                ["-config.file=/etc/tempo.yaml"],
            )
            prometheus = run(
                "prometheus",
                prometheus_image,
                [
                    "--tmpfs",
                    "/prometheus:uid=65534,gid=65534,size=256m",
                    "-v",
                    str(prometheus_config) + ":/etc/prometheus/prometheus.yml:ro",
                    "-v",
                    str(ROOT / "gateway/observability/alerts.yml")
                    + ":/etc/prometheus/alerts.yml:ro",
                    "-v",
                    str(ROOT / "gateway/observability/slo.yml")
                    + ":/etc/prometheus/slo.yml:ro",
                ],
                [
                    "--config.file=/etc/prometheus/prometheus.yml",
                    "--web.enable-remote-write-receiver",
                    "--enable-feature=exemplar-storage",
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
            source_map = {source["uid"]: source["jsonData"] for source in sources}
            assert source_map["prometheus"]["exemplarTraceIdDestinations"] == [
                {"name": "traceID", "datasourceUid": "tempo"}
            ]
            trace_metrics = source_map["tempo"]["tracesToMetrics"]
            assert trace_metrics["datasourceUid"] == "prometheus"
            assert all(
                "$__tags" in query["query"] and "$$" not in query["query"]
                for query in trace_metrics["queries"]
            )
            checks["provisioned_correlations"] = source_map

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
            assert len(dashboards) == 12
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
                                        "status": {"code": 1},
                                    }
                                ]
                            }
                        ],
                    }
                ]
            }
            # A real client/server span pair exercises Tempo's service graph.
            client_id = secrets.token_hex(8)
            client_span = {
                "traceId": trace_id,
                "spanId": client_id,
                "parentSpanId": payload["resourceSpans"][0]["scopeSpans"][0]["spans"][
                    0
                ]["spanId"],
                "name": "synthetic-local-call",
                "kind": 3,
                "startTimeUnixNano": str(now - 8_000_000),
                "endTimeUnixNano": str(now - 1_000_000),
                "status": {"code": 1},
            }
            payload["resourceSpans"][0]["scopeSpans"][0]["spans"].append(client_span)
            payload["resourceSpans"].append(
                {
                    "resource": {
                        "attributes": [
                            {
                                "key": "service.name",
                                "value": {
                                    "stringValue": "qualification-synthetic-worker"
                                },
                            }
                        ]
                    },
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    **client_span,
                                    "spanId": secrets.token_hex(8),
                                    "parentSpanId": client_id,
                                    "kind": 2,
                                }
                            ]
                        }
                    ],
                }
            )
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
                        "query": (
                            "{ resource.service.name = "
                            '"grafana-qualification-synthetic" }'
                        ),
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
            # Wait for actual remote write, not an injected look-alike metric.
            prom_base = port(prometheus, 9090)
            exemplar_url = (
                prom_base
                + "/api/v1/query_exemplars?"
                + urllib.parse.urlencode(
                    {
                        "query": "traces_spanmetrics_latency_bucket",
                        "start": now / 1e9 - 60,
                        "end": now / 1e9 + 120,
                    }
                )
            )
            deadline = time.monotonic() + 90
            while True:
                exemplars = request(exemplar_url)
                if trace_id in json.dumps(exemplars):
                    break
                assert time.monotonic() < deadline, (
                    "Tempo remote write did not deliver its trace exemplar"
                )
                time.sleep(2)
            (output / "actual-tempo-exemplars.json").write_text(
                json.dumps(exemplars, indent=2) + "\n"
            )
            checks["actual_tempo_remote_write_exemplar"] = {
                "trace_id": trace_id,
                "series": len(exemplars["data"]),
            }
            # Rates need two exported samples. Keep sending bounded real spans
            # until both RED and service-graph counters exhibit positive rates.
            rate_queries = {
                "span_rate": "sum(rate(traces_spanmetrics_calls_total[1m]))",
                "edge_rate": "sum(rate(traces_service_graph_request_total[1m]))",
                "duration_p95": (
                    "histogram_quantile(0.95, sum by (le) "
                    "(rate(traces_spanmetrics_latency_bucket[1m])))"
                ),
            }
            batches = 0
            deadline = time.monotonic() + 90
            while True:
                rate_samples = {
                    name: request(
                        prom_base
                        + "/api/v1/query?"
                        + urllib.parse.urlencode({"query": expression})
                    )["data"]["result"]
                    for name, expression in rate_queries.items()
                }
                if all(
                    samples
                    and any(
                        math.isfinite(float(item["value"][1]))
                        and float(item["value"][1]) > 0
                        for item in samples
                    )
                    for samples in rate_samples.values()
                ):
                    break
                assert time.monotonic() < deadline, (
                    "Real Tempo trace rates did not become measurable"
                )
                another = json.loads(json.dumps(payload))
                another_id = secrets.token_hex(16)
                another_now = time.time_ns()
                for resource in another["resourceSpans"]:
                    for scope in resource["scopeSpans"]:
                        for span in scope["spans"]:
                            span["traceId"] = another_id
                            span["startTimeUnixNano"] = str(another_now - 10_000_000)
                            span["endTimeUnixNano"] = str(another_now)
                request(port(tempo, 4318) + "/v1/traces", another)
                batches += 1
                time.sleep(5)
            checks["real_trace_positive_rates"] = {
                "extra_batches": batches,
                "samples": rate_samples,
            }
            # Keep rule intervals unchanged. This fixture cannot establish a 7-day SLO.
            deadline = time.monotonic() + 65
            while True:
                coverage = request(
                    prom_base
                    + "/api/v1/query?"
                    + urllib.parse.urlencode(
                        {"query": "ambicrafted:slo_observed_ratio7d"}
                    )
                )
                if len(coverage.get("data", {}).get("result", [])) == 3:
                    break
                if time.monotonic() >= deadline:
                    (output / "slo-chain-failure.json").write_text(
                        json.dumps(
                            {
                                "ratios": coverage,
                                "targets": request(prom_base + "/api/v1/targets"),
                                "rules": request(prom_base + "/api/v1/rules"),
                                "buckets": request(
                                    prom_base
                                    + "/api/v1/query?"
                                    + urllib.parse.urlencode(
                                        {
                                            "query": (
                                                "ambicrafted_aura_operation_duration_seconds_bucket"
                                            )
                                        }
                                    )
                                ),
                            },
                            indent=2,
                        )
                    )
                    raise AssertionError(
                        "The candidate SLO recording chain did not evaluate"
                    )
                time.sleep(2)
            checks["synthetic_slo_chain"] = coverage["data"]["result"]
            assert (
                request(
                    prom_base
                    + "/api/v1/query?"
                    + urllib.parse.urlencode(
                        {"query": "ambicrafted:slo_budget_remaining7d"}
                    )
                )["data"]["result"]
                == []
            )
            checks["budget_unknown_before_full_coverage"] = True
            exemplar_result = request(
                base + "/api/ds/query",
                {
                    "from": str(now // 1_000_000 - 60_000),
                    "to": str(time.time_ns() // 1_000_000),
                    "queries": [
                        {
                            "refId": "A",
                            "datasource": {"type": "prometheus", "uid": "prometheus"},
                            "expr": "traces_spanmetrics_latency_bucket",
                            "exemplar": True,
                            "range": True,
                            "instant": False,
                            "intervalMs": 1000,
                            "maxDataPoints": 100,
                        }
                    ],
                },
                auth=True,
            )
            assert not exemplar_result["results"]["A"].get("error")
            assert trace_id in json.dumps(exemplar_result), (
                "Grafana did not return the actual Tempo exemplar trace ID"
            )
            (output / "grafana-exemplar-query.json").write_text(
                json.dumps(exemplar_result, indent=2) + "\n"
            )
            checks["grafana_exemplar_query_trace_id"] = trace_id
            checks["actual_service_graph"] = request(
                prom_base
                + "/api/v1/query?"
                + urllib.parse.urlencode(
                    {"query": "traces_service_graph_request_total"}
                )
            )["data"]["result"]
            assert checks["actual_service_graph"], (
                "No edge derived from the real synthetic span pair"
            )
            rules = request(prom_base + "/api/v1/rules")
            assert all(
                rule["health"] == "ok"
                for group in rules["data"]["groups"]
                for rule in group["rules"]
            )
            checks["rules_evaluated_without_error"] = sum(
                len(group["rules"]) for group in rules["data"]["groups"]
            )
            expressions = set()
            for filename in sorted((provisioning / "json").glob("*.json")):
                dashboard = json.loads(filename.read_text())
                for link in dashboard.get("links", []):
                    if link.get("url", "").startswith("/d/"):
                        assert link["url"].split("/")[2] in {
                            entry["uid"] for entry in dashboards
                        }
                for panel in dashboard["panels"]:
                    for target in panel.get("targets", []):
                        if "expr" in target:
                            expressions.add(
                                target["expr"]
                                .replace("$__rate_interval", "1m")
                                .replace("$__range", "5m")
                            )
            panel_results = []
            for expression in sorted(expressions):
                data = request(
                    base + "/api/ds/query",
                    {
                        "from": str(time.time_ns() // 1_000_000 - 300_000),
                        "to": str(time.time_ns() // 1_000_000),
                        "queries": [
                            {
                                "refId": "A",
                                "datasource": {
                                    "type": "prometheus",
                                    "uid": "prometheus",
                                },
                                "expr": expression,
                                "instant": True,
                                "range": False,
                                "intervalMs": 1000,
                                "maxDataPoints": 100,
                            }
                        ],
                    },
                    auth=True,
                )
                item = data["results"]["A"]
                assert not item.get("error"), {
                    "expr": expression,
                    "error": item.get("error"),
                }
                numeric_values = [
                    value
                    for frame in item.get("frames", [])
                    for index, field in enumerate(
                        frame.get("schema", {}).get("fields", [])
                    )
                    if field.get("type") == "number"
                    for value in frame.get("data", {}).get("values", [])[index]
                    if isinstance(value, (int, float)) and math.isfinite(value)
                ]
                panel_results.append(
                    {
                        "expr": expression,
                        "frames": len(item.get("frames", [])),
                        "finite_values": len(numeric_values),
                    }
                )
            (output / "dashboard-query-results.json").write_text(
                json.dumps(panel_results, indent=2) + "\n"
            )
            checks["all_panel_queries_valid"] = len(panel_results)
            for query in [
                "ambicrafted:slo_coverage7d",
                "ambicrafted_browser_web_vital_seconds_count",
                "ambicrafted_browser_layout_shift_ratio_count",
                "ambicrafted_aura_first_token_seconds_count",
                "ambicrafted_aura_operations_total",
            ]:
                samples = request(
                    prom_base
                    + "/api/v1/query?"
                    + urllib.parse.urlencode({"query": query})
                )["data"]["result"]
                assert samples and all(
                    math.isfinite(float(item["value"][1])) for item in samples
                ), query
                if query.endswith("coverage7d"):
                    assert all(
                        0 < float(item["value"][1]) < 0.01 for item in samples
                    ), "Short fixture must not claim full coverage"
            checks["finite_rum_aura_samples_and_partial_coverage"] = True
            if browser:
                assert not set(dashboard_uids) - {
                    entry["uid"] for entry in dashboards
                }, "Unknown requested dashboard UID"
                rendered_dashboards = [
                    entry
                    for entry in dashboards
                    if not dashboard_uids or entry["uid"] in dashboard_uids
                ]
                # Synthetic temporary credentials enter via stdin, never argv,
                # shell history, test reports or browser screenshots.
                process = subprocess.run(
                    ["node", str(browser)],
                    input=json.dumps(
                        {
                            "base": base,
                            "password": password,
                            "dashboards": rendered_dashboards,
                            "root": str(ROOT),
                            "output": str(output),
                        }
                    ),
                    capture_output=True,
                    text=True,
                    timeout=900,
                    check=False,
                )
                (output / "browser-stderr.log").write_text(
                    process.stderr.replace(password, "[redacted]")
                )
                assert process.returncode == 0, "Browser qualification failed"
                checks["browser"] = json.loads(process.stdout)
            assert source_hashes == {
                str(path.relative_to(ROOT)): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in source_paths
                if path.is_file() and "__pycache__" not in path.parts
            }, "Candidate configuration changed during qualification"
            result["ok"] = True
    finally:
        cleanup_failures = []
        if exporter:
            exporter.shutdown()
            exporter.server_close()
        if exporter_thread:
            exporter_thread.join(timeout=5)
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
    parser.add_argument("--prometheus-image", default=PROMETHEUS)
    parser.add_argument("--tempo-image", default=TEMPO)
    parser.add_argument(
        "--dashboard-uid",
        action="append",
        default=[],
        help=(
            "Limit browser rendering to an existing UID; all backend queries still run"
        ),
    )
    args = parser.parse_args()
    qualify(
        args.image,
        args.output.resolve(),
        args.browser,
        args.prometheus_image,
        args.tempo_image,
        args.dashboard_uid,
    )
