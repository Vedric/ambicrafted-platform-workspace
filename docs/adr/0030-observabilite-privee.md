# 0030 — Private operational telemetry

Date: 2026-09-29. Status: accepted.

The native service dashboards did not expose console latency, retained work,
voice processing, queue pressure or backup freshness. Monitoring must distinguish
no traffic, unknown measurements, failure and stale data without exporting client
content or distributing the console credential to containers.

The control API owns a per-process Prometheus registry. ASGI middleware measures
completed HTTP responses, including streaming and cancellation, with a fixed set
of capability/outcome labels. Routes, user IDs, file names, request bodies and
conversation content are excluded. `/api/metriques` requires the CLI credential;
a browser session cannot read it. Database summaries are numeric aggregates.
Retained runs, token measurements and costs are gauges, because retention and
deletion can reduce them. Missing usage is never converted to a free API call.

A user-systemd timer collects the authenticated endpoint locally and publishes
an atomic, aggregate-only textfile every thirty seconds after completion. A
minimal node exporter reads that directory; all default collectors are disabled.
It has no host port, Docker socket, host root mount or credential. Prometheus
scrapes it over the existing private Compose network. An API failure replaces
the previous API snapshot with explicit failure, and a stopped collector is
detected through its timestamp. The dashboards hide stale application gauges.

Linux/WSL resource statistics, bounded NVIDIA numeric probes and local backup
manifest freshness are included. GPU figures cover shared GPU use; WSL figures
do not measure all Windows memory. A completed manifest is not proof of restore
or an off-host copy. The collector does not export client paths or device names.

Three native Grafana views have English/French variants and stable datasource
UIDs. `plateforme-sre` remains the English home UID, preserving existing links.
No unsigned visualization plugin or custom JavaScript is required. Rules produce
local alerts; there is no external notification destination by default.

The exporter binary is built from pinned upstream source with a pinned corrected
Go toolchain and module lock. The original image's HIGH findings were not waived.
The full image scanner includes this eighth image alongside the optional Neo4j
runtime. Functional CI and image-security qualification remain separate gates.

Tests cover credential boundaries, bounded labels, streaming cancellation,
retention semantics, failed/oversized/unexpected collection, atomic publication,
managed systemd units, rule firing and recovery. A deterministic generator checks
dashboard JSON in CI. See [monitoring operations](../MONITORING.md).

References: [Prometheus naming](https://prometheus.io/docs/practices/naming/),
[instrumentation](https://prometheus.io/docs/practices/instrumentation/),
[textfile collector](https://prometheus.github.io/client_python/exporting/textfile/),
[Grafana dashboard practices](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/best-practices/).
