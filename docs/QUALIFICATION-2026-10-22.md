# Personal workstation qualification — 22 October 2026

This candidate is suitable for assessment as a **supervised personal workspace**.
It is not accepted as an autonomous engineering expert, a multi-tenant hosted
service or a vulnerability-free system. Publishing its source changes none of
those boundaries. Console/API versions remain 0.5.0, workflow 0.2.0 and speech
0.3.3.

The application freeze is `6e216d36f68dc0136d7b96cf463463d79e534ff9`.
The candidate additionally contains the separately qualified image-security
changes and documentation. Application source remains unchanged from this freeze.
Release evidence must identify the final commit, hosted run, actual installed
revision and endurance outcome separately; do not infer completed hosted gates,
endurance or live promotion from this source document.
See [releases](https://github.com/Vedric/ambicrafted-platform-workspace/releases)
and [Actions](https://github.com/Vedric/ambicrafted-platform-workspace/actions).
The [21 October assessment](QUALIFICATION-2026-10-21.md) remains historical.

## Defects reproduced and corrected

An inference wrapper could exit while a descendant retained its protocol pipes.
Cancellation then skipped the process group because the leader had already
exited, leaving the worker and shared inference access blocked. The new regression
uses a real fork and a descendant that ignores SIGTERM. Cancellation signals the
owned group and completes forced cleanup even after leader exit.

An already authorized JSON/Markdown export or PNG conversion could finish after
session invalidation had been observed by the browser and still download private
content. Asynchronous exports now observe the browser's session invalidation
and logout events and recheck cancellation before download. This final check
does not make a new server authorization request.
Native image/canvas callbacks cannot all be interrupted; their late completion
cannot publish an export. Resources are released on success, timeout and abort.

An independent counterexample then exposed session discovery returning HTTP200
with `connecte=false`, without the HTTP401 event used by the first fix. Session
transition and explicit logout now notify the same cancellation path. Browser
regressions exercise both HTTP401 and HTTP200-disconnected paths, including real
PNG conversion.

Additional real API tests cover concurrent duplicate operations, disconnects
before/after commit, storage rollback, opposite approval races and the production
dialogue rate window. Browser tests use a one-second test-server window with the
real limiter and unchanged eight-request maximum; a separate API contract tests
the actual 60-second production window using a controlled monotonic clock. The browser fixture is not a rate-limit
configuration for deployment.

## Reproducible functional evidence

The product freeze was cloned without operator `.env`, pre-existing virtual
environments or shared console `node_modules`. Locked installation preceded
tests, lint, typing, packaging and dependency audits.

| Check | Observed result and boundary |
| --- | --- |
| Control API | 802 tests; 85% combined statement/branch coverage |
| SRE workflow | 259 tests; 88% coverage |
| Runbooks MCP | 48 tests; 74% coverage |
| Console unit tests | 302 tests across 27 files; build, typing and formatting pass |
| Speech runtime | 109 unit tests; 71% coverage; 25 real offline tests and 9 overlapping AVX2 regressions pass |
| Configured Playwright matrix | 250/250 pass, zero retries; desktop/mobile Chromium and critical Firefox/WebKit projects; 12.3 minutes |
| Evaluation expectations | 12 tests; 73 consumed regression cases, no unseen holdouts |
| Configuration | Secret-input hook, example-only Compose, generated dashboards and Prometheus rule tests pass |
| Runtime dependencies | Four Python and two npm audits report zero known advisories; LiteLLM installed-package audit is separate below |

Coverage includes statements and branches, not every child-process instruction.
Tests of actual subprocesses, browsers and disposable services provide separate
behavioral evidence. No 100% coverage or exhaustive pentest claim is made.

The crafted HTTP qualification sent **341 requests** to its own real disposable
API. It exercised missing/forged authentication, Host/Origin/CSRF refusal,
cross-site requests, malformed/oversized inputs, ticket replay, logout revocation
and path-confusion probes against a private canary. SQLite remained consistent;
no forbidden analysis or conversation message was created. This is a bounded
adversarial probe, not an independent penetration-testing certification.

The development lifecycle exercise completed **1,004 cycles in 1,201.778 seconds**,
with 8,161 requests, 167 descendant checks and three server starts. Its peak RSS
was 126,476 KiB with 11 file descriptors and one thread; SQLite integrity passed.
The release evidence separately records the requested **two-hour frozen-source
exercise**, its final status and resource/latency samples. Inference in this
exercise is synthetic: it tests HTTP, queue, subprocess, restart and persistence
behavior, not sustained GPU throughput or 24-hour availability.

The 250 configured browser cases comprise 88 desktop Chromium, 88 mobile
Chromium, 32 critical Firefox, 37 critical WebKit and five Firefox motion checks.
They cover the configured journeys, not every feature on every engine. Twelve
additional English visual captures cover desktop/mobile and both themes without
observed overlap or horizontal overflow. Only deliberately injected HTTP503
errors appeared in that visual exercise.

A separate real-time Firefox audio probe initially stayed suspended despite a
trusted click and active user activation. Changing autoplay preferences did not
fix it. Providing a private PulseAudio null sink with the original preferences
made the same probe run in a fresh browser instance and yielded nonzero
measured audio (RMS 0.1066).
The cause was the test runtime's absent audio output; no application code or
matrix assertion was relaxed. This software-output check does not establish
physical speaker or microphone behavior.

## Actual recovery, including negative cases

The existing private backup was encrypted using age 1.3.1, decrypted into a new
private location and restored into disposable database services. Its 18 files
totaled 389,832,298 bytes. Inventory before and after matched; the source backup
was not changed. Validation found 91 PostgreSQL tables, 31 Qdrant points,
consistent SQLite state, five conversations/16 messages, three analyses/two
checkpoints and the retained graph-memory note. No browser session or one-use
ticket was restored.

Ten adverse archive conditions were rejected without a partial destination:
wrong identity, existing destination, truncation, modified ciphertext, path
traversal, symbolic link, hard link, FIFO, duplicate member and invalid inventory.
The complete encrypt/decrypt/database exercise took approximately 27 seconds
on this workstation; this is not a promised recovery-time objective.

A separate nonempty synthetic application drill reopened a report, LangGraph
checkpoint, conversation, extracted CSV and two Neo4j notes with their relation
through the application repositories. These exercises establish same-host
recovery behavior. An independently protected off-host copy and its key custody
remain unproved until the operator completes that separate exercise.

## Security snapshot

The eight final local image identities, evaluated with Trivy 0.74.0 and the
database updated **22 October 07:10:52 UTC**, have **0 CRITICAL, 0 HIGH,
23 MEDIUM, 9 LOW and 5 UNKNOWN** package/advisory occurrences. They are not
counts of exploitable paths, and zero HIGH does not mean zero vulnerabilities.
The release workflow rebuilds and scans all eight images independently; its
later database and image identities can legitimately produce different counts.

The initial scan identified a HIGH in LiteLLM's Wolfi certificate bundle. The
correction uses the signed native `ca-certificates-bundle=20260909-r3`, with its
complete bundle hash and 118 effective trust anchors verified. Old and tampered
stores fail the qualification. [ADR 0049](adr/0049-paquet-ca-wolfi-natif.md).

The Python audit also rejected pypdf 6.19.0 for five advisories. API and LiteLLM
now use **6.21.1**. Trivy already reported these as four MEDIUM and one LOW:
the difference was the audit threshold, not an absent vulnerability database.
The final LiteLLM image's 199 installed Python distributions have zero reported
advisories, with no ignored finding. Its synthetic auth, restricted aliases,
streaming, embeddings, structured output, restart and logical rollback pass.

The subsequent compatible fixes update LiteLLM's native libc family,
PostgreSQL's musl/zlib and gosu dependencies, Grafana's musl, Neo4j's JLine
family, and Qdrant's three affected Rust lock entries and dashboard dependencies.
The complete Qdrant native trust store and the exact Comodo AAA distrust in
Prometheus and the metrics exporter are also qualified. LiteLLM application
files, PostgreSQL's server/entrypoint and Grafana application/plugin files
compare byte-for-byte with their preceding qualified versions. The final
LiteLLM Python inventory remains the same 199 audited distributions.
[ADR 0052](adr/0052-correctifs-images-compatibles.md) records the decision and
[the dependency register](DEPENDENCIES.md) explains the residual findings.

The final Qdrant r4 Docker build took **14 minutes 52.8 seconds**, with a
measured Rust compiler cgroup peak of **8.8203 GiB**, including file cache.
Rust compiled from source; unchanged dashboard, healthcheck and trust-helper
stages used existing cache. This is not a fully uncached build measurement or a
hosted-runner duration guarantee. The r4 synthetic migration, search,
persistence, snapshot recovery and three Chromium dashboard views pass under
**Docker's default seccomp**, with no external browser requests, page errors
or cleanup failures. The separate upstream persisted-hashmap tests needed a
test-only io_uring seccomp extension; it was not applied to the deployed runtime.

The following are exact **local image IDs**, not registry digests or the
identities of separately rebuilt CI images. Tags use the `ambicrafted/`
namespace. All rows have zero CRITICAL/HIGH; M/L/U are package/advisory
occurrences. Existing image generations and reports remain preserved.

| Local image tag | Exact local image ID | M / L / U |
| --- | --- | ---: |
| `litellm:1.104.4-stable-security.20261022.2` | `sha256:e35ae0923cb2390347ef3ecec1db023325c28f20059e19f151664ca4f3b0fffc` | 0 / 0 / 0 |
| `postgres:16.15-alpine-security.20261022.2` | `sha256:996e5b41aa3aa9e556c8db65a7ceb08e453b8b2eaa211806311ccee69c76b004` | 0 / 0 / 0 |
| `qdrant:1.19.2-security.20261022-r4` | `sha256:a73326e19ff4c617a2662b6e490a1e6e8569d2c3a0fe5382954cf4ee14874562` | 23 / 8 / 0 |
| `grafana:13.2.4-security.20261022.2` | `sha256:74e980c0c95cd1c5367882183adf1d80f60e0175e0df5ab7ea7b1491b483399d` | 0 / 0 / 1 |
| `prometheus:3.15.0-security.20261022` | `sha256:7eb4b64d260f950f061dfd5d5cd023e5e2915234ec349e3883f753441f11161d` | 0 / 0 / 2 |
| `platform-metrics:1.12.1-security.20261022` | `sha256:3d61be203211b1cb7e755da74ad1423d20deb2d7cdd59be4ad4d741c31ef5a9c` | 0 / 0 / 1 |
| `neo4j:5.26.32-memory.20261022` | `sha256:01dae1b7e86152078159661fcbe550b69fba711101cb9f115e1db7c9c30bd626` | 0 / 1 / 0 |
| `tempo:3.0.3-security.20261021` | `sha256:c40ff8fc5994ace7feabdabd5e80f13a08d48f074c5b6c6f335fb0316dfd0412` | 0 / 0 / 1 |

The host certificate store requires its own
[administrative verification](HOST-TOOLS.md#host-certificate-trust-and-uv).

## Agent usefulness: the remaining product boundary

One pass per case compared the same six regressions and local runtime. The retained
change only clarifies when to search a procedure, read a result or ask for missing
incident observations. It does not weaken provenance, review or human approval.

| Experiment | Mechanical acceptance | Subsequent engineering AI review | Observed tokens |
| --- | ---: | ---: | ---: |
| Baseline, six cases | 1/6 | 0/6 | 126,758 |
| Automatic-repair prototype, not adopted | 2/6 | 1/6 | 116,893 |
| Retained prompt clarification, same cases | 3/6 | 1/6 | 108,534 |
| Four newly sealed cases, retained implementation | 2/4 | 1/4 | 75,461 |

The automatic-repair attempt produced no demonstrated successful correction
attributable to that mechanism, so the extra calls/state were removed.
[ADR 0050](adr/0050-recherche-utile-et-correction-non-retenue.md).
The new cases were executed on clean signed source `a47812ba6aa5e57c8a5ffd4240b224e5f8478383`,
whose agent implementation is unchanged in the product freeze. Expectations
were sealed before execution. The four cases are now regressions; none remains
an unseen holdout.

Observed failures include generic abstention on answerable questions, insufficient
reasoning about restored evidence and an overly broad permission conclusion.
One retained regression run exceeded its 30,000 observed-token threshold to
30,767 when the last call completed; post-call accounting is not a prepaid cap.
Neither these small stochastic samples nor the automated review establishes
general accuracy. AI-assisted engineering review is **not independent human
acceptance**. A mechanically valid proposal can still be wrong or unhelpful.

## Publication and personal acceptance

History, Git blobs, PR references, GitHub logs/artifacts/releases and license
notices were reviewed before publication. One historical zero-job workflow run
had unavailable logs (HTTP404); no claim is made to have inspected that archive.
Private raw API metadata, operator backups, credentials and model outputs are
excluded from public evidence. Third-party licenses remain applicable: publishing
project source is not authorization to redistribute all images or model weights.

The [hybrid deployment decision](adr/0051-deploiement-personnel-hybride.md) retains
eight containers plus the native supervised application. The UI keeps automatic
motion, accessible reduced-motion behavior, both languages and both themes.
The [personal walkthrough](PERSONAL-USE.md) gives a complete first session.

Before relying on this workstation for important work, the operator must still:

1. Accept physical microphone/speaker behavior and speech quality in both languages.
2. Review proposals on representative personal tasks; the evaluation failures
   above preclude autonomous operational trust.
3. Prove recovery from an independent encrypted copy with separately protected keys.
4. Choose and test an external alert recipient if unattended notification is needed.
5. Complete host administration and reboot/second-machine checks where required.

These are explicit boundaries of the personal release, not unfinished work
silently described as production acceptance. A stable or commercial label needs
its own measured acceptance criteria and evidence.
