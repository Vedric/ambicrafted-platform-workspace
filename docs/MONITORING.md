# Monitoring the private platform

Open [Grafana](http://localhost:3000/d/plateforme-sre) on the platform machine.
Grafana keeps its own authentication; the console does not embed its password.
Use the dashboard links to switch between six views and English/French:

| View | English UID | French UID | What to inspect |
|---|---|---|---|
| Mission control | `plateforme-sre` | `plateforme-sre-fr` | Service availability, collection freshness, requests, queue, disk and backups |
| Agentic activity | `plateforme-agentic` | `plateforme-agentic-fr` | Retained runs and decisions, API/voice latency, measured SRE tokens, knowledge inventory |
| Infrastructure | `plateforme-infrastructure` | `plateforme-infrastructure-fr` | Linux CPU/memory/disk, shared GPU, scrape health and native service telemetry |
| Reliability & budgets | `plateforme-slo` | `plateforme-slo-fr` | Observed SLIs, seven-day collection coverage, budget remaining, paired burn windows and exclusions |
| Browser & conversation | `plateforme-experience` | `plateforme-experience-fr` | First-visible-period LCP/INP/CLS, sample counts, first text and completed-operation latency |
| Traces & correlation | `plateforme-traces` | `plateforme-traces-fr` | Received span RED metrics, measured service edges, exporter losses and local log investigation |

Grafana's theme setting supports both light and dark. Panels use explicit units,
legends and thresholds. Hover for values, select a time range and use Explore for
details. Dashboards refresh every thirty seconds. A fresh installation needs
traffic and several samples before rates and percentiles become meaningful.
Native surfaces follow Grafana's light/dark theme. Time-series lines do not
interpolate across missing samples or smooth away abrupt changes. The console's
Observability page links to these views in the selected interface language.

## A practical investigation

1. Open Mission control and inspect collection age before interpreting service
   status. A service probe tests an endpoint, not an inference or a recovery.
2. Open Reliability & budgets. Compare eligible event count, exclusions and
   coverage with the observed ratio. HTTP success can coexist with an AURA
   delivery failure; the two populations are intentionally separate.
3. For slowness, use Browser & conversation. Compare first-text duration,
   completed operations and speech-server duration. RUM measures a different
   boundary and is not a complete microphone-to-speaker round trip.
4. Open Traces & correlation. A Tempo span-metric exemplar links to the trace.
   From a span, follow the provisioned service-metrics link. A service graph
   needs paired, propagated client/server spans; an empty edge is not proof of
   an idle or disconnected service.
5. Match its exact trace ID with a content-free API event in the private local
   service journal. Inspect locally, without publishing raw logs:

   ```sh
   journalctl --user -u ambicrafted-console.service --since '30 min ago' -o cat
   ```

Loki and centralized log search are **not installed**. The corrected Grafana
distribution includes only Prometheus and Tempo plugins. Reintroducing a log
backend requires a separately qualified image/plugin, private ingestion policy,
retention and recovery procedure; a datasource entry alone is insufficient.

## Objectives, coverage and error budget

The following personal operating objectives are provisional policy, not a
contractual SLA or a statement that the platform has already met them:

| SLI | Seven-day target | Denominator and limitations |
|---|---|---|
| API transport | 99.9% success | Successful + server-error responses for selected business groups; excludes auth, probes, telemetry, 4xx and cancellation |
| AURA delivery | 99% success | Admitted terminal success + error + timeout; excludes replay and cancellation; success is technical delivery, not factual correctness |
| AURA duration | 95% ≤30 seconds | Successful server operations only; assess delivery failure alongside it; excludes capture/playback |

`gateway/observability/slo_definitions.py` is the reviewed policy source. Regenerate
rules and dashboards together after changing an objective. Do not silently apply
new targets to a historical contractual report. Ratios use reset-aware counter
increases and aggregate observations before division; they are not averages of
per-instance percentages. The application currently has one process: do not
extrapolate this qualification to untested multi-worker aggregation.

An empty denominator stays unknown. During warm-up, the observed SLI uses the
available part of the window; coverage is shown beside it. The remaining budget
is hidden until all seven days are observable at the 15-second rule interval.
Coverage is recorded from exporter health, snapshot freshness, API collection and
metric presence. It measures collection continuity, not proof that every request
was captured; counter updates between the last scrape and a process crash can
be lost. An overspent budget is negative. Collection gaps make it unavailable
again. Prometheus retains at most fourteen days or 2 GB, whichever limit is reached
first; it does not provide thirty-day reporting or off-host durable storage.

Paired-window alerts use seven-day burn rates: >3.36× on both 5 m and 1 h, or
>1.4× on both 30 m and 6 h, sustained for two minutes after the condition is observed. Recording and alert
groups have independent evaluation phases: allow additional 15-second evaluation
ticks; this is not an exact wall-clock delivery deadline. The corresponding 2% per hour / 5% per six hours
are budget-spend projections at comparable traffic, not measured fractions of
the seven-day event budget when traffic changes. Both windows require at
least twenty eligible events and complete collection. This controls noise at
low volume but can suppress an important single failure: absolute outcome counts,
refusals, cancellations and readiness checks remain necessary. Alert state is
local; no delivery to a person or acknowledgement is proven.

## Browser privacy and measurement boundary

RUM runs only for a document whose initial resolved session is authenticated.
A document first opened anonymously is excluded until reload. The initial
route is reduced to one of ten fixed categories. The first hidden transition
flushes at most three final values, one each for LCP, INP and CLS, through the
existing same-origin session and CSRF controls. The initial browser performance
buffer can include rendering before the authentication query resolves; this
is a document measurement, not a temporal isolation boundary. No retry queue persists.
This covers the first visible period, not every SPA navigation or the entire
session. Unsupported measurements and pages without interactions remain absent.
Browser lifecycle termination can lose the batch; values are client-reported,
not trustworthy security/audit evidence. Percentiles need their sample counts.

The strict endpoint rejects bearer credentials, arbitrary fields, invalid route
categories, nonfinite values, oversized bodies and excessive batches. It accepts
no page content, full URL, DOM attribution, user agent, session identifier or
stack trace. Only aggregate histograms survive. The client uses the standard
`web-vitals` build without attribution data or an external analytics destination.

## Trace privacy and failure behavior

The API's explicit OpenTelemetry provider exports to the fixed loopback Tempo
OTLP endpoint in bounded background batches. It ignores inbound tracing/baggage
headers and environment-driven exporter destinations, headers and proxies.
Attributes are enumerations or measurements; prompts, documents, source paths,
exception text and request bodies are excluded. Propagation to the confidential
local model gateway links instrumented downstream work; it does not create spans
for uninstrumented services.

The span counters distinguish queued, sent, failed and dropped. Queued includes
sent/failed; do not add all categories. Sent means OTLP accepted the batch, not
that it is durable or searchable. Tempo failure does not block an AURA response.
The pending/in-flight queue is limited to 256 spans. HTTP transport applies a
two-second timeout per network I/O and a two-second response-body window, not
an absolute two-second deadline for the entire export.
Abrupt shutdown, queue limits and retention can leave incomplete traces. Set
`PLATFORM_TRACING=0` to disable API export. A trace records technical execution,
not the truth of a model's conclusions.

## Installation

Build and configure the console/API through the normal installation first, then:

```sh
./plateforme observabilite installer
docker compose --project-directory gateway up -d --build platform-metrics
docker compose --project-directory gateway up -d --no-deps --force-recreate prometheus tempo grafana
systemctl --user status ambicrafted-metrics.timer --no-pager
```

On a checkout with a changed Grafana Dockerfile, include `--build` when updating
Grafana. Follow the backup and qualification steps in [Operations](OPERATIONS.md)
before upgrading existing services. These commands touch the named services only.
Recreating Prometheus and Tempo refreshes their file bind mounts and reloads the
changed scrape/rule/trace configuration; a plain `up -d` can leave the existing
process/configuration running. Named data volumes are retained. On an existing
installation these restarts briefly interrupt collection; qualify the changes,
preserve a verified backup and use a maintenance window. The expanded API metrics
and tracing require rebuilding/restarting the API through its normal installer;
dashboard provisioning alone does not instrument application code.
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
