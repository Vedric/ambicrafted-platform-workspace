# Qualification — 20 October 2026

This record distinguishes the implementation candidate from the live workstation
and from release approval. The supported product is a private Linux/WSL workspace
for one trusted operator. It is not a remote multi-tenant service, an autonomous
remediation system, or a guarantee of defect-free operation.

## Candidate changes

- Mandatory document isolation: rootless namespaces, read-only filesystem,
  seccomp, bounded output, cancellation-safe cleanup and an actual readiness probe.
- Complete backup inventory, explicit mission-source inclusion, encrypted age
  export and safe import into a new staging directory. Checksums cover the bytes
  actually archived, including the regression where a source changes and reverts.
- Real local workflow qualification: 39 regression scenarios and 12 new,
  independently authored holdouts, with separate mechanical contracts and expert
  review. The old Promptfoo dependency tree was removed; historical fixtures
  remain archived. No external judge runs implicitly.
- A structural triage boundary: a model's free-form justification cannot deliver
  an unsupported cause or remediation before the sourced, supervised proposal.
- Cross-engine critical journeys and an explicit download link for WebKit export.
- Targeted dependency/image fixes, independent image jobs and a gated release draft.
- Host prerequisites installable privately from verified artifacts and tested
  under the service's actual isolation properties.
- Structured extraction and triage through the confidential local alias.
  Reasoning can compare its derived summary against original observations in
  ephemeral context; that added message is never appended to durable history.
  Generated derivatives remain confidential and can still contain identifiers.

## Committed application qualification

The full hosted application workflow passed on commit
`5de2fa3525f07649fb7af3d1dc61ffb20f34a64e`:
[Actions run 39456794556](https://github.com/Vedric/ambicrafted-platform-workspace/actions/runs/39456794556).
All eight jobs succeeded, including the four Python projects, console/browser
journeys, real offline speech, evaluation configuration, secret hook and Compose
validation. This includes the changed agent and volume-selection implementation.
It proves that revision; subsequent application changes need their own qualification.

Independent clean-clone evidence also includes:

| Revision and scope | Observed result |
| --- | --- |
| `45a47abd`, four locked Python environments | 889 pytest cases pass; 26 script tests and 10 qualification-contract tests pass; lint, typing, builds and applicable coverage thresholds pass |
| `5d8e0af2`, changed agent and full Python rerun | 896 pytest cases pass; 26 script tests and 11 qualification-contract tests pass; four fresh locked environments, lint, typing, builds and applicable coverage thresholds pass |
| `5de2fa35`, recovery volume configuration | Six tests and twelve synthetic Compose renders pass in a clean clone, including custom project names and explicit volume selectors |
| `1fb46446`, console | 249 unit tests and 120 Playwright tests pass; build, TypeScript checks, formatting and npm audit pass |
| `1fb46446`, real voice | 23 native FR/EN tests and 9 AVX2 regression tests pass with verified local models in an isolated network namespace |
| `1fb46446`, control lifecycle | 1,801.689 seconds, 799 cycles, 7,235 HTTP requests, three startups, read p95 28.14 ms; SQLite integrity OK |

The browser set covers Chromium desktop/mobile, Firefox and WebKit Linux,
including motion, real tutorial audio decoding, synthetic microphone flows,
authentication, keyboard accessibility, attachments and conversation history.
It does not certify physical microphones/speakers or every Safari/iOS version.
The speech exercise includes a negative network control and before/after model
hashes; proxy settings alone are not its isolation proof.

The lifecycle exercise uses the real API, SQLite, queue and subprocess boundary
with deterministic inference. Observed RSS was 89,808–90,516 KiB and file
descriptors 8–9. It is not a 24-hour soak, GPU capacity test or proof of no memory
leak under all workloads.

The first hosted API attempt exposed Ubuntu 24.04 AppArmor restrictions on
unprivileged namespaces. CI now loads Ubuntu's vendor bubblewrap profile only
after a verified permission-denied probe. The successful hosted job kept
AppArmor and the user-namespace restriction enabled. No global sysctl bypass or
unsandboxed document fallback was introduced.

One initial local SIGTERM integration test timed out. Three targeted reruns,
the full affected module, subsequent fresh-clone API runs and hosted API tests
passed without increasing its timeout. Its original cause remains unexplained;
it is retained as an observation rather than claimed as a diagnosed repair.

## Service and recovery exercises

These additional measurements used isolated synthetic services or explicitly
identified live snapshots. They are not all final-commit CI results.

| Exercise | Observed result |
| --- | --- |
| Synthetic recovery | A mission, actual LangGraph checkpoint, saved conversation, extracted CSV attachment, two Neo4j notes and relationship survive encrypted export/import and restoration |
| Neo4j migration | 5.26.31 → 5.26.32 persistence, auth, scope filtering, uniqueness, restart and logical rollback pass |
| LiteLLM migration | Restricted key survives migration/restart; unauthorized access and external alias rejected; real local streaming/embedding, structured schema compatibility and logical rollback pass |
| Qdrant migration | Ranking, filtering, aliases, updates/deletion, restart, snapshot recovery and rollback into a separate old-version volume pass |
| Grafana | 13 signed plugins accepted, six EN/FR dashboards, 102 rendered panels, real Prometheus query/Tempo trace, no browser JS exception |
| Host service restrictions | Synthetic document extraction and age availability pass with NoNewPrivileges, PrivateTmp, ProtectSystem and private umask |
| Live backup `20261020T154425Z` | Complete inventory restored into disposable services: 86 PostgreSQL tables, 31 Qdrant points, five source files, two conversations/six messages; 16 file hashes verified; auth sessions/tickets excluded |

The live snapshot had no saved analyses or memory notes, so it cannot prove
recovery of those nonempty objects; the separate synthetic recovery exercise
does. Individual live database snapshots were consistent, but writers were not
quiesced across all stores during that initial backup. A coordinated promotion
requires a separate stopped-writer snapshot and preservation of old state.

## Agent quality: contracts and meaning

The first real local-model run used clean commit `1fb46446`, the actual LangGraph
workflow and semantic retrieval over synthetic sources. **33 of 39 mechanical
contracts passed**. Three cases failed extraction validation and three exhausted
bounded tool/token budgets. Independent AI engineering review classified
19 outputs as usable with reservations, 14 as requiring correction, and six as
unassessable because no proposal completed. This is explicitly **not human
acceptance**.

Counterexamples exposed a real information bottleneck: reasoning only saw a
model-generated summary. That summary sometimes changed a proposed deployment
into an executed incident, a measured reference into an acceptance threshold,
or a near-limit metric into proven saturation. Exact source attribution alone
does not establish relevance or causal correctness.

[ADR 0038](adr/0038-observations-originales-et-sorties-contraintes.md) records the
correction: original observations are compared locally in ephemeral context,
incident and design-review prompts are distinguished, and extraction/triage use
JSON Schema generation followed by application validation. Confidential routing,
source guards, budgets and human approval remain mandatory.

An 11-case development rerun passed ten mechanical contracts. Review still
identified semantic defects and one budget-exhaustion regression. Those results
are retained, not discarded as retries. All 39 consulted cases are now regression
cases. Twelve new cases were independently written, kept private until the SRE
implementation was frozen, then committed for a fresh 51-case run. Human review
records remain pending; no automated process supplies an operator signature.

The subsequent 51-case run used clean commit `5d8e0af2` and completed in
1,028.983 seconds with 803,694 reported tokens. Median case duration was
18.617 seconds and p95 was 24.237 seconds. **44 of 51 mechanical contracts
passed: 35/39 regression cases and 9/12 new holdouts.** Three cases exhausted
their budgets and four completed but failed a contract. No remediation was
executed.

Independent AI review of the 39 regression outputs classified 27 as usable
with reservations, ten as requiring semantic correction and two as having no
completed proposal. The first independent review of the twelve holdouts found
eight meeting its four quality thresholds, but only **six passing both the
quality review and mechanical contracts**. Remaining substantive defects
include a contradictory certificate-validity claim, incorrect recovery-time
comparison, an unjustified statistical assertion and incomplete ARM64
qualification advice. Two confidence-contract failures have prudent prose but
ambiguous confidence calibration; their thresholds were not relaxed after
seeing the results.

These are single generations, not a statistical reliability estimate. Better
regression results do not establish general expert competence. The run used
the existing LiteLLM 1.102.1 gateway, Qdrant 1.19.1 in an isolated qualification
service and Ollama 0.32.15 with recorded model digests. It does not qualify
these outputs against the replacement service images. The result SHA-256 is
`e8f3f9f0782c5ba3181a1f2a12c860faf281b85475a9bba6f976101e88eb7453`.

## Image gate

Trivy 0.74.0 full candidate scans on 20 October, without advisory suppression:

| Component | CRITICAL | HIGH |
| --- | ---: | ---: |
| LiteLLM stable 1.104.4 + aiohttp/yarl patch | 0 | 0 |
| PostgreSQL 16.15 + rebuilt gosu | 0 | 0 |
| Tempo 3.0.3 + Go/x/net rebuild | 0 | 0 |
| Prometheus 3.15.0 + Go/x/net rebuild | 0 | 0 |
| Grafana 13.2.4 + core fix and official signed plugins | 0 | 56 |
| Qdrant 1.19.2 + minimal runtime and rebuilt UI | 0 | 1 |
| Platform metrics exporter + Go/x/net rebuild | 0 | 0 |
| Neo4j 5.26.32 memory profile on UBI10 | 0 | 0 |

**The HIGH/CRITICAL release gate remains failed.** Grafana findings reside in
official signed plugin binaries; rebuilding them locally while disabling
signature enforcement is not an accepted workaround. The Qdrant finding is
`braces` 3.0.3 in the full frontend dependency SBOM, with no corrected release
available at this review. This finding's build/runtime applicability must be
distinguished from exploitation; it is retained rather than removed from the
inventory. See the image READMEs and ADRs 0035–0037.

The independent hosted rebuild and scan also completed for all eight images on
`bb029913`, with no scan error and the same total of zero CRITICAL and 57 HIGH:
[Actions run 39454781148](https://github.com/Vedric/ambicrafted-platform-workspace/actions/runs/39454781148).
Six image jobs passed; Grafana and Qdrant failed the vulnerability threshold.
Earlier hosted disk-capacity failures were repaired by freeing specified
preinstalled SDK directories on GitHub-hosted Linux runners and checking free
space. That repair does not suppress findings or change workstation storage.

## Remaining acceptance boundaries

- Qualify the final changed revision before publication; the passing hosted
  revision above does not automatically cover subsequent changes.
- Stable release approval remains blocked by the stated image gate.
- Select an off-host encrypted backup destination and keep its recovery identity
  separately. A local encrypted round trip does not test loss of the workstation.
- Configure a real notification destination and verify receipt. Prometheus rules
  and Grafana panels alone are not delivered incident notifications.
- Qualify browser permission, microphone, speakers and French/English AURA speech
  on the actual devices. Automated synthetic audio has a different scope.
- Validate recovery/startup on a second supported machine and agree RPO/RTO.
  User lingering is enabled on this workstation; Windows/WSL still needs to run.
- Expert acceptance must review representative agent outputs, sources and
  uncertainty. Mission presets share a supervised workflow and are not eighteen
  independently validated specialist agents.

Full local evidence is kept outside Git under the private
`/home/vedric/platform/production-2026-10-20/` directory. Do not publish raw model
outputs, credentials, databases or recovery archives as portfolio material.
