# Personal qualification — 24 October 2026

This checkpoint concerns console/API 0.5.0, SRE workflow 0.2.0 and speech 0.3.3
on the private Linux amd64 workstation. It supersedes the **current status** of
the [23 October assessment](QUALIFICATION-2026-10-23.md), while preserving its
failures and historical evidence. It does not certify arbitrary hardware,
multi-tenant production or autonomous expert correctness.

## GPU recovery and real conversation

After the operator's Windows update/reboot, the host reports WSL **3.0.3.0**,
kernel **6.18.54.1-1** and NVIDIA driver **617.42**. Linux `nvidia-smi` exits
successfully and detects the RTX 5090. The observed Windows boot timestamp is
24 October 12:29:16.5 UTC. The old WSL GPU-access failure is resolved at this
checkpoint; this does not establish which individual Windows component caused it.

Actual AURA requests through the running UI API and local gateway pass English
generation, a French follow-up using the prior conversation, cancellation,
replay protection, inference-lease release and removal of the synthetic
conversation. The installed source and image were unchanged during this test.

| Real streamed turn | First text | Completion |
|---|---:|---:|
| English, initially unloaded model | 20.079 s | 20.599 s |
| French contextual follow-up, warm model | 0.530 s | 1.172 s |
| Cancellation probe, warm model | 0.537 s | 0.542 s |

These are individual measurements, **not p95 estimates or guarantees**. Twenty-two
GPU observations show the entire 18,777,144,031-byte model resident in VRAM;
GPU utilization reaches 95%. The existing authenticated-entry preparation and
24-hour retention request reduce repeated cold loads; available memory, other
GPU workloads and service restarts can still require a cold load.

The installed preparation check reports **20/20 passed**, including document
isolation, local voice and MCP handshakes. A separate complete gateway exercise
after recovery passes all seven checks in 101.176 seconds. The newly corrected
LiteLLM image then passes the same full profile in 90.752 seconds: authenticated
restricted aliases, real streaming/structured output/embeddings, actual OTLP
parent/state propagation, key persistence, restart and independent-database
rollback. Synthetic prompts only; this does not validate model reasoning.

## Cache and browser behavior

[ADR 0054](adr/0054-cache-public-et-revalidation-console.md) replaces the custom
file lookup with Starlette's static-file implementation. Hashed public build
assets are immutable; HTML and named media revalidate. Private API responses
retain `no-store`. Missing modules/media return real HTTP404 responses rather
than the SPA HTML. HEAD, conditional HTTP304 and video byte ranges remain usable.

In new desktop and mobile Chromium contexts, the first navigation transfers
**900,836 bytes** for five measured versioned assets. A second actual document
navigation transfers **zero bytes** for those assets; 899,336 decoded resource
bytes are reused. This measures those public assets, not all traffic or inference.

The complete Playwright matrix passes **258/258**, with no failed, skipped,
flaky or retried case: 33 Firefox critical cases, 38 WebKit critical cases,
five Firefox motion cases, and 91 Chromium cases each on desktop/mobile.
It takes 991.942 seconds. Coverage includes authentication/logout, diagrams,
documents, history, guides, responsive layout, animations and accessibility.
Inference in this browser matrix is deterministic test data. It does not use
the operator's microphone or certify audible quality on physical speakers.

The API passes **827 tests** after the PDF update. The cache load check sends
256 real loopback HTTP requests at concurrency 16 in 0.355 seconds, with a
34.411 ms p95. These are local measurements on this host, not internet capacity
or a multi-user scalability benchmark. The original run with an incomplete test
PATH correctly failed 29 sandbox checks; after adding the verified `bwrap`
tool, those checks pass. No parser isolation or timeout was relaxed.

The voice runtime passes **109 unit tests** and, separately, **25 real-model
tests** in a network-isolated namespace in 129.12 seconds. Those include both
languages, technical terms, repeated turns and real audio containers. Physical
audio permissions, hardware capture and the operator's listening acceptance
remain separate.

## Fresh security findings and corrections

Trivy **0.74.0**, with its database updated at **24 October 13:07:23 UTC**, first
reports nine HIGH occurrences in the previously installed images. That failure
is retained. [ADR 0055](adr/0055-dependances-corrigees-et-contrat-filelock.md)
documents the corrections and the explicitly qualified local LiteLLM dependency
contract. No finding, package path, unknown severity or unfixed advisory is hidden.

| Image | CRITICAL | HIGH | MEDIUM | LOW | UNKNOWN |
|---|---:|---:|---:|---:|---:|
| Grafana | 0 | 0 | 0 | 0 | 1 |
| LiteLLM | 0 | 0 | 1 | 0 | 0 |
| Neo4j | 0 | 0 | 0 | 1 | 0 |
| Platform metrics | 0 | 0 | 0 | 0 | 1 |
| PostgreSQL | 0 | 0 | 0 | 0 | 0 |
| Prometheus | 0 | 0 | 0 | 0 | 2 |
| Qdrant | 0 | 0 | 23 | 8 | 0 |
| Tempo | 0 | 0 | 0 | 0 | 2 |
| **Total** | **0** | **0** | **24** | **9** | **6** |

These are package/advisory occurrences, not distinct exploitable paths.
Qdrant's residual Debian records have no fixed version listed in this database.
The LiteLLM OTel MEDIUM remains visible despite its separately verified source
backport. Neo4j's LOW remains alongside the documented vendor LTS backport.
UNKNOWN records stay visible. The dispositions in
[ADR 0052](adr/0052-correctifs-images-compatibles.md) and
[ADR 0053](adr/0053-retroportage-tracestate-litellm.md) still apply.

Fresh pip-audit 2.10.1 checks find zero known vulnerabilities in the locked
production dependencies: control API 74 packages, voice 25, SRE agent 67 and
Runbooks MCP 48. The local editable project is excluded by name, not a third-party
advisory. The installed LiteLLM image's 27 filelock and 63 pypdf wheel files match
the official fixed wheels byte-for-byte, excluding installer-managed RECORD.

| Changed image | Qualified local identity |
|---|---|
| `ambicrafted/grafana:13.2.4-security.20261024.1` | `sha256:3f4187233880350e6acdeed1726c72d14d036930232fc4d35d1b2869cb552730` |
| `ambicrafted/litellm:1.104.4-stable-security.20261024.2` | `sha256:893661a17a680fc1c8cf1577a1cd6488af57dbe0135546c5f9e48c0bd14366da` |
| `ambicrafted/qdrant:1.19.2-security.20261024.1` | `sha256:128569ee32e8e750985b4a84860e22e2f02f7edefb7de82ecb94fbe29f36dac3` |

Qdrant passes migration from the actual prior 1.19.2 image, search/payload indexes,
writes/deletion, restart, old/new snapshot restoration and three Chromium views.
The undici regression fails with 6.29.0 and passes with 6.29.1, demonstrating
that the fix addresses the malformed-response crash.

Grafana passes authentication, plugin signatures, all dashboard queries,
Prometheus/Tempo correlations, real OTLP/exemplars/service graphs, SLO/error-budget
semantics and **48 Chromium dashboard/theme/viewport variants**, with no clipped
or overlapping panels or external requests. Synthetic data labels and incomplete
coverage remain truthful. An initial run under `umask 077` exposed unreadable
temporary Tempo/Prometheus configs. The verifier now explicitly makes only those
public fixture configs readable by their non-root containers; credentials remain
0600. The complete rerun under the same restrictive umask passes in 142.405 seconds.

## Fresh-clone native privacy finding

The first fresh clone of signed commit `9005cfff1402fb62718fefe603beca527874fe71`
passed its completed agent, MCP, voice and console test stages, but its final
clean-tree assertion correctly rejected a native `:memory:.ses` file. Import
probes locate this behavior in ONNX Runtime/Piper. The minimal test environment
exposed a dependency on an ambient opt-out; the API child environment also did
not explicitly carry that native setting. The two API encryption failures in
this first clone separately came from selecting the older system age binary
instead of the qualified 1.3.1 tool; those failures are retained.

[ADR 0056](adr/0056-confidentialite-native-du-runtime-vocal.md) adds the native
opt-out before package imports and explicitly to API child startup. Four new
fresh-process tests initialize the real native library with a contradictory
inherited setting and require no persisted state. Native syscall observation
shows no IPv4/IPv6 socket creation or session file in the corrected import;
a separate socket control validates the observer. The short old probe creates
the session file but also shows no socket creation. This is not evidence of
historical data exfiltration. After the correction, all **138 voice tests** pass together in a network-isolated
namespace in 135.57 seconds: 113 unit/native-bootstrap cases and 25 real-model
cases, with no skip. The 45 voice API tests also pass. The earlier 109-test unit
count predates the four new native-bootstrap cases.

The fresh clone's full browser matrix subsequently passes **258/258** in
822.860 seconds, with zero skips, failures or flaky cases. Console build,
304 unit tests, browser-test typing and formatting also pass. This receipt is
bound to commit `9005cfff1402fb62718fefe603beca527874fe71`; the privacy follow-up
changes voice startup and the API's child environment, not the console tree.
The source commit is GitHub-signed, its remote tree matches the GitGuardian-scanned
index exactly, and its signature is independently verified with GitHub's official
public key in a temporary verification keyring. The operator's local signing key
remains locked after reboot; signing policy and private keys were not changed.

## Final clean-environment verification

A second fresh remote clone at signed commit
`2ec349f6fe36187563e0946df5985675bdcce373` passes all stages and remains clean.
It uses the qualified age 1.3.1 executable explicitly, with no private `.env`.
Network-isolated unit jobs pass 827 API, 259 agent, 48 Runbooks and 113 voice
cases; the 25 real-model voice cases run in the separate fully passing suite
above. The console passes 304 unit tests. Coverage thresholds, lint, typing,
packages, standalone script locks, evaluation contracts, 64 maintenance tests
and the 60-second lifecycle/restart/cancellation exercise pass.

The secret hook, example-only Compose validation, generated dashboard check,
Prometheus rule tests and both npm advisory audits pass. The initial Prometheus
rule invocation cannot read the deliberately private clone as the container's
default user; rerunning the same pinned image as the source owner's UID passes.
No product rule, source permission or security check is relaxed. All initial
failures and successful reruns remain in the private evidence manifest.

The browser receipt above is reused because the complete console source tree
is identical between the two signed commits. The privacy change is additionally
covered by native-process and API tests; this reuse is not a claim that a third
browser matrix was executed.

## Hosted offline-startup finding

The first hosted image gate at commit `7d012a36a981f7c469480ffa88be067694076e95`
correctly rejects the LiteLLM build. Its real concurrent CLI test exposes a
remote cost-catalog retry racing with Python module initialization while
networking is disabled. The earlier local passing build did not establish
that this import was reliable. No retry of that unchanged failed job is used.

[ADR 0057](adr/0057-catalogue-local-demarrage-passerelle.md) selects the supported
bundled-catalog setting before imports in both the build and runtime. The new
`.20261024.2` image passes the real consumer checks and the full GPU gateway
profile, all seven checks, in **82.345 seconds**. Its fresh scan reports zero
HIGH/CRITICAL and the same single visible OTel MEDIUM. The other seven exact
image identities and their existing scan/qualification receipts are unchanged.
The old image/scan receipts remain available alongside this replacement.

Cloud cost estimates now use the pinned bundled metadata until a reviewed
image/catalog update or explicitly verified deployment price is applied; they
must not be represented as live vendor prices or an invoice. Actual token
measurements remain separate. The four-process import/lock test additionally
refuses Python socket connects and DNS operations, within Docker's networkless
build stage. No upstream application source is patched for this setting.

## Installed workstation and hosted gates

The reference installation was updated to signed main commit
`05937ab4d19e7fa53189be91b26d675fbac0119f` at **2026-10-24T17:17:12.841804+00:00**.
[Application CI](https://github.com/Vedric/ambicrafted-platform-workspace/actions/runs/40112335915)
and the [eight-image gate](https://github.com/Vedric/ambicrafted-platform-workspace/actions/runs/40112378638)
pass all sixteen required jobs on that exact commit. Hosted rebuilds report the
same 0 CRITICAL, 0 HIGH, 24 MEDIUM, 9 LOW and 6 UNKNOWN occurrences; their image
IDs remain separate from the qualified local builds installed above.

The first strict collection rejected delayed GitHub job-step metadata even though
jobs had finished. Finalized logs, successful job/run conclusions and artifacts
verified against GitHub's SHA-256 digests corroborate completion. The original
rejection and raw pending step states remain recorded. No workflow was retried,
no scan finding suppressed, and no failed job was accepted as successful.

The installation stopped application writers, made a fresh backup and verified
logical restoration, including PostgreSQL tables, rows, roles and sequences.
Cold state/environment copies and old image archives were retained. Container
replacement was limited to the three qualified images; source, console build and
API/voice dependencies were updated to their reviewed versions.
Existing data, configuration and the other five container identities were checked;
original schedulers were restored. Authenticated readiness passes **20/20**;
anonymous access and unauthorized gateway aliases remain refused.

A new real GPU exercise on the installed source passes context retention,
streaming, replay without duplication, cancellation and fixture cleanup.
The first measured English text arrives in **3.397 s**,
and the French contextual follow-up in **0.527 s**.
These are individual warmed-workstation observations, not a latency SLO.

| Installed synthetic speech round trip | ASR | First generated text | Reply synthesis | Total after input audio |
|---|---:|---:|---:|---:|
| FR | 8.610 s | 0.533 s | 0.666 s | 10.063 s |
| EN | 12.138 s | 0.524 s | 0.484 s | 13.360 s |

Each round trip sends synthesized input through the real ASR, local GPU dialogue
and TTS endpoints, verifies stored context and deletes only its own synthetic
conversation. It does not capture a physical microphone or establish perceived
voice quality. Returned audio remains private and non-cacheable. CPU recognition
dominates the measured 10–13-second end-to-end delay. Instant spoken interaction
is not established; further recognition optimization needs its own accuracy
regression checks, since earlier faster decoder settings changed important words.

Four additional live Chromium welcome/guide variants cover light/dark themes at
1440 px and 390 px. Continuous AURA motion advances, no horizontal overflow or
page error is detected, video playback/seek and caption toggling work. Repeat
navigation reuses the measured public assets without retransferring them.
The first mobile probe waited for an offscreen animation; the harness was corrected
to scroll the emblem into view before measuring its resumed animation. That failed
probe is retained; product visibility/energy-saving behavior was unchanged.
These installed-browser probes complement the fresh 258-case browser matrix;
they do not replace its Firefox/WebKit coverage. HTTP checks separately verify
HTML revalidation, immutable assets, real video byte ranges and private no-store
responses. The source and image identities remain unchanged during acceptance.

## Publication and remaining acceptance

The source changes and data-preserving personal installation are complete at
the measured commit above. A subsequent documentation-only commit records these
results; it does not claim the runtime was tested again at its own future hash.
The older signed `v0.5.0-rc.3` tag remains unchanged and its release remains an
unpublished draft. A new tagged release still needs an available signing key,
its required tagged application/image qualification and final acceptance review.
The operator's local signing key remains locked after the host reboot.

The [personal walkthrough](PERSONAL-USE.md) describes the supported use. Physical
microphone/speaker acceptance, an independently stored encrypted recovery copy,
and second-machine recovery still need separate evidence. The previous reasoning
holdout remains only 1/4 acceptable; model output requires human review. These
limits are not repaired by a faster GPU or green functional tests. No claim of
zero defects, zero vulnerabilities or unsupervised expert autonomy is made.
