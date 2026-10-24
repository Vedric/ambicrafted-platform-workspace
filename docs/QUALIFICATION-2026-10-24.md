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
| `ambicrafted/litellm:1.104.4-stable-security.20261024.1` | `sha256:34224ed37f43ecfaad1816444c8ecbc1dfaba6110ae34fc85356169f0c2220fd` |
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

## Publication and remaining acceptance

Local proofs do not substitute for the required hosted application and image
gates, a data-preserving installation, or the final release review. Their exact
commit/run/installation records are appended when completed. The older signed
`v0.5.0-rc.3` tag is not moved to represent this newer source.

The [personal walkthrough](PERSONAL-USE.md) describes the supported use. Physical
microphone/speaker acceptance, an independently stored encrypted recovery copy,
and second-machine recovery still need separate evidence. The previous reasoning
holdout remains only 1/4 acceptable; model output requires human review. These
limits are not repaired by a faster GPU or green functional tests. No claim of
zero defects, zero vulnerabilities or unsupervised expert autonomy is made.
