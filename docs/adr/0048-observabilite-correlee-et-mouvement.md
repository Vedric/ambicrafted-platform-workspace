# Correlated local observability and automatic motion

Date: 2026-10-21

Status: accepted for implementation; runtime qualification and promotion are separate.

## Context

HTTP success was insufficient to measure AURA delivery: a streamed HTTP 200 can
contain an application error. The existing dashboards had no browser measurements
and the API did not contribute spans to Tempo. Fourteen-day Prometheus retention
with a 2 GB size ceiling cannot support an unconditional thirty-day SLO claim.
The operator also requested removal of the persistent motion toggle.

## Decision

Extend ADR 0030 with bounded, content-free application outcomes, browser vitals
and API tracing. Preserve the private authenticated textfile metrics bridge.
Never make a customer, conversation, document, trace or operation identifier a
Prometheus label. The new RUM endpoint accepts a strict finite schema under the
existing browser session, CSRF, origin, body-size and rate controls; it refuses
CLI credentials. It stores only aggregate observations, not payloads or sessions.

RUM covers the first visible period of an initially authenticated document.
It reports at most one LCP, INP and CLS value, attributed to a fixed route category.
It does not measure every internal SPA navigation, an entire long session or an
unauthenticated welcome page. Browser-reported values are not attested evidence.
Missing or unsupported measurements remain absent, and sample counts accompany
percentiles. Client telemetry does not enter the business HTTP denominator.

AURA counters describe admitted terminal attempts, with separate error, timeout
and cancellation states. Successful delivery means technical completion, not
semantic correctness or audible playback. Idempotent replays and admission
refusals have separate counters. The legacy nonstreaming endpoint retains its
existing timeout-to-error behavior rather than changing user behavior for a
metric. Response streams and traces never expose raw exceptions.

Use the official OpenTelemetry SDK and protobuf encoder with an explicit
provider, bounded background export and a fixed local OTLP destination. Do not
inherit trace headers, baggage, resource attributes, proxies or exporter secrets
from untrusted requests/environment. Export failure must not delay a response.
Only enumerated/numeric attributes and safe structured events are emitted.
Trace IDs correlate local journal events and Tempo spans; they remain outside
metric labels. Tempo-generated span metrics carry exemplars, with provisioned
Grafana links back to Tempo and from spans to service metrics. This does not
create a central log store: Loki is absent from the qualified Grafana distribution.

Define three provisional personal operating objectives over seven days:

| Objective | Target | Eligible population |
|---|---|---|
| API transport | 99.9% successful | Selected business groups, success + server error |
| AURA delivery | 99% delivered | Admitted success + error + timeout, excluding cancellation and replay |
| AURA duration | 95% within 30 s | Successful operations only, server work through completion |

These are not contractual SLAs, uptime measurements or model-quality acceptance.
Display exclusions, absolute failures and observation coverage beside ratios.
Do not replace a zero denominator with one or manufacture healthy missing data.
Budget remaining is available only after a full seven-day collection window.
It may become negative after overspending. Shorter observed ratios remain useful
during warm-up but are identified as observed data. Retention pressure and
collection gaps can make the budget unavailable again.

Use paired-window burn alerts adapted to seven days: 3.36× over both 5 m and 1 h
(2% budget/hour), 1.4× over both 30 m and 6 h (5% budget/six hours). Both windows
require at least twenty events and complete collection. Single low-volume
failures remain visible through absolute counts and service checks. Alerts are
local; no external delivery or acknowledgement is implied.

Supersede ADR 0029's manual motion override and the manual-pause portion of ADR
0015. Remove the toggle and migrate its old storage keys. Motion follows the OS
accessibility preference, runs automatically when allowed, and pauses offscreen
or in hidden documents. The same lifecycle applies to CSS, SVG and React motion.
No control is provided to force motion against an OS reduction preference.

## Alternatives rejected

- A thirty-day ratio over fourteen days of retained samples, or a permanent
  green 100% when no requests occurred: both overstate the evidence.
- Treating all HTTP 200 streams as successful work: hides application failures.
- Calling a client-measured percentile a server SLO or a contractual SLA.
- Sending browser text, URLs, DOM attribution or stack traces for convenience.
- Automatically adding Loki or unqualified plugins: the current signed minimal
  Grafana build intentionally excludes them; restoring that capability requires
  its own maintained dependency, security, storage and recovery qualification.
- Animating offscreen content continuously or retaining a hidden persisted
  motion-off preference after removing its UI control.

## Consequences

Operators gain separate transport, delivery, latency, browser and trace signals,
with explicit limitations. More panels do not establish resilience or correctness.
The monitoring plane stays single-host; off-host encrypted recovery, external
alert receipt and representative human acceptance remain separate requirements.
Local journal correlation is supported; centralized searchable logs are not.
SDK batching can lose spans on abrupt termination and telemetry gaps invalidate
the budget window. RUM exclusions reduce coverage intentionally.

Native Grafana panels preserve light/dark theme behavior and avoid custom scripts
or plugins. Reproducible generators validate grid bounds and overlap. Promtool
tests cover missing data, application failures inside HTTP success, low volume,
burn windows and recovery. Browser qualification must additionally check actual
queries, correlation links, responsive layouts and both themes in isolation.

References: [Google SRE alerting on SLOs](https://sre.google/workbook/alerting-on-slos/),
[Prometheus histograms](https://prometheus.io/docs/practices/histograms/),
[Tempo span metrics](https://grafana.com/docs/tempo/latest/metrics-from-traces/span-metrics/span-metrics-metrics-generator/),
[Tempo provisioning](https://grafana.com/docs/grafana/latest/datasources/tempo/configure-tempo-data-source/provision/),
[Prometheus exemplars](https://grafana.com/docs/grafana/latest/datasources/prometheus/configure/).
Official references were checked on 21 October; Context7 was unavailable due to
its monthly quota, so primary documentation was used directly.

Burn-rate spend projections assume comparable traffic across windows. They
are not the actual fraction of the seven-day event budget spent during a
traffic surge or quiet period. The ratios and eligible counts remain separate.
