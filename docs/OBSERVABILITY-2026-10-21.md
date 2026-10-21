# Observability and motion qualification — 21 October 2026

This update adds operational measurements to the private, single-operator
platform. It does not establish commercial availability, a contractual SLA or
the factual correctness of AURA's responses. Installation and operation are
documented in [Monitoring](MONITORING.md); the design decision is
[ADR 0048](adr/0048-observabilite-correlee-et-mouvement.md).

## Delivered behavior

- Six native Grafana views in English and French, with light/dark rendering,
  units, legends, sample counts and drilldowns. CLS retains three decimal places.
- Separate transport, AURA delivery and successful-operation latency objectives.
  Seven-day budgets remain unknown during incomplete collection; alerts combine
  short/long burn windows and minimum traffic. No alert recipient is configured.
- Bounded, content-free local OpenTelemetry export and Prometheus/Tempo exemplar
  links. A local journal trace ID supports investigation; Loki is not installed.
- Authenticated browser measurements for the first visible period of an
  initially authenticated document. This is not whole-session or SPA navigation
  RUM. Telemetry accepts finite numeric samples, fixed metric/route categories,
  a browser cookie, Origin and CSRF; bearer credentials are refused.
- Automatic interface animations. The Motion control and saved overrides are
  removed. The system reduced-motion preference, offscreen and hidden-tab pauses
  remain effective.

## Local candidate evidence

The private qualification records retain source hashes, commands, failures and
corrected runs. These results describe the reviewed local candidate, not a
hosted CI run or proof of installation on another machine.

| Boundary | Observed result |
|---|---|
| Control API | 794 tests passed; branch-aware coverage 84%; Ruff, mypy and package build passed |
| Python dependency audit | No known runtime vulnerability reported; resolved package versions unchanged |
| Console | Initial full unit run: 295 passed; final changed behavior: 34 targeted tests passed; TypeScript, formatting and build passed |
| Browser regression | 100 distinct selected scenarios passed across the retained executions, including Chromium desktop/mobile and Firefox/WebKit motion checks; not one uninterrupted full-suite run |
| Final console visuals | Four light/dark desktop/mobile variants passed accessibility and overflow checks |
| Alert rules | Ten existing and eight new fixtures passed, including missing data, failed delivery inside HTTP 200, low volume, collection loss, fast/slow burn recovery and counter restart |
| Independent SLO review | 17 additional counterexamples passed; dense seven-day simulation was not run because the pinned promtool loader caps an individual input series at 10,000 samples |
| Grafana integration | 103 distinct queries accepted, 90 rules evaluated: 78 SLO rules (72 recording and six alerting) plus 12 existing rules; real OTLP traces, Tempo-generated span/service metrics, remote-write exemplars and Grafana trace-ID correlation checked |

Grafana qualification covers 48 language/theme/viewport variants using isolated
synthetic traffic. After correcting CLS precision and low-rate rounding, the
unchanged variants were reused by configuration hash and affected variants were
rendered again. One intermediate browser run blocked a single attempted request
outside its fixture; its origin was not captured by the initial harness. The
instrumented reproduction passed without an outside request. The original cause
remains unexplained, and diagnostics now persist blocked origins immediately.
This is not evidence that no such attempt can ever recur.

The initial alert fixture also exposed nondeterministic evaluation order between
recording groups. Test order is now explicit, with firing assertions allowing
evaluation-phase delay. The production rule expressions were not weakened.

Browser tests use synthetic records and disposable credentials. They cannot
prove physical microphone selection, speaker output or the subjective quality
of a spoken conversation. A successful OTLP acknowledgement is not a durability
guarantee. Export loss and missing measurements remain visible.

## Decisions that remain separate

Earlier real-model evaluations exposed reasoning and evidence-validation
failures. This instrumentation does not change that acceptance result; human
review remains necessary. External alert delivery, encrypted off-host backups
with independently held recovery keys, host certificate trust verification and
physical audio acceptance are still distinct operational work.

The installed Qdrant follow-up on source `f5ba5017040c` was separately backed up,
restored in isolation and verified. Its eight-image local scan found zero
CRITICAL/HIGH, with 42 MEDIUM, 12 LOW and seven UNKNOWN occurrences remaining.
Its application CI and targeted Qdrant image CI passed. Those results must not
be attributed to another commit or used to relabel the earlier failed release.

CI remains deliberately batched. Required publication gates are retained; no
general-purpose self-hosted runner is attached to this private workstation.
