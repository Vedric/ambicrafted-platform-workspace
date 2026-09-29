# Monitoring the private platform

Open [Grafana](http://localhost:3000/d/plateforme-sre) on the platform machine.
Grafana keeps its own authentication; the console does not embed its password.
Use the dashboard links to switch between three views and English/French:

| View | English UID | French UID | What to inspect |
|---|---|---|---|
| Mission control | `plateforme-sre` | `plateforme-sre-fr` | Service availability, collection freshness, requests, queue, disk and backups |
| Agentic activity | `plateforme-agentic` | `plateforme-agentic-fr` | Retained runs and decisions, API/voice latency, measured SRE tokens, knowledge inventory |
| Infrastructure | `plateforme-infrastructure` | `plateforme-infrastructure-fr` | Linux CPU/memory/disk, shared GPU, scrape health and native service telemetry |

Grafana's theme setting supports both light and dark. Panels use explicit units,
legends and thresholds. Hover for values, select a time range and use Explore for
details. Dashboards refresh every thirty seconds. A fresh installation needs
traffic and several samples before rates and percentiles become meaningful.

## Installation

Build and configure the console/API through the normal installation first, then:

```sh
./plateforme observabilite installer
docker compose --project-directory gateway up -d --build platform-metrics
docker compose --project-directory gateway up -d prometheus grafana
systemctl --user status ambicrafted-metrics.timer --no-pager
```

On a checkout with a changed Grafana Dockerfile, include `--build` when updating
Grafana. Follow the backup and qualification steps in [Operations](OPERATIONS.md)
before upgrading existing services. These commands touch the named services only.
The installer preserves unrelated systemd units and refuses to replace an
unmanaged unit with the same name. Linux user-systemd is required for scheduling.

For an explicit collection or an existing observability summary:

```sh
./plateforme observabilite collecter
./plateforme observabilite
```

The default command retains its previous summary behavior. Aggregate snapshots
are written under ignored `gateway/observability/.textfile/`. The collector holds
the existing private CLI credential; it is never mounted in Prometheus or the
exporter. The exporter exposes no additional host port. Grafana and Prometheus
remain bound to loopback by the existing Compose configuration.

## Read the measurements correctly

- A missing metric is unknown. It is not zero, healthy, or free. Freshness gates
  hide stale application values after ninety seconds. Check collection health
  before interpreting a quiet graph.
- HTTP histograms measure server response duration, including the complete
  response stream. Voice durations exclude microphone capture, frontend work
  and speaker playback. They are not the full conversational round trip.
- Runs, conversations, documents and SRE token/cost sums cover retained local
  records. They can decrease after deletion. The coverage graph shows how many
  reports actually include a usage measurement. AURA token usage is not included
  in these SRE totals. Reported API cost excludes workstation electricity/hardware.
- Service probes cover the existing readiness endpoints. They do not prove
  model correctness, successful agent completion or the quality of graph memory.
- GPU utilization belongs to the whole shared device. Linux/WSL CPU and memory
  cover the VM. A completed local backup manifest does not prove a successful
  restoration, encryption at rest or an off-machine copy.

## Alerts and recovery

Prometheus evaluates every fifteen seconds. Rules cover missing exporter,
stale collector, API collection failure, unhealthy services, sustained API errors,
queue pressure, low disk/memory, old backups and a configurable GPU warning.
The error-rate alert requires at least twenty requests in ten minutes to avoid
misleading percentages at very low volume. Rule tests exercise failure/recovery.

Alerts are local only; no email, Slack or paging destination is configured.
If the collector becomes stale, inspect `ambicrafted-metrics.service` and its
timer. If API collection fails, check the console service and private local
configuration. If the exporter is unavailable, inspect only `platform-metrics`
and its Prometheus target. Never run global Docker cleanup on a shared machine.

To pause collection without deleting data:

```sh
systemctl --user stop ambicrafted-metrics.timer
```

Versioned dashboards and rules live in `gateway/observability`. Regenerate JSON
with `uv run --no-project --python 3.14 gateway/observability/build_dashboards.py`;
CI checks it with `--check` and runs the pinned Prometheus rule tests. See
[ADR 0030](adr/0030-observabilite-privee.md) for the privacy boundary.
