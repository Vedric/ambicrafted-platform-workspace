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
- Real local workflow qualification: 39 synthetic scenarios, separate mechanical
  contracts and expert review. The old Promptfoo dependency tree was removed;
  historical fixtures remain archived. No external judge runs implicitly.
- A structural triage boundary: a model's free-form justification cannot deliver
  an unsupported cause or remediation before the sourced, supervised proposal.
- Cross-engine critical journeys and an explicit download link for WebKit export.
- Targeted dependency/image fixes, independent image jobs and a gated release draft.
- Host prerequisites installable privately from verified artifacts and tested
  under the service's actual isolation properties.

## Development evidence completed

These measurements were made in the isolated candidate worktree. They are not
represented as final-commit CI results.

| Exercise | Observed result |
| --- | --- |
| Synthetic recovery | A mission, actual LangGraph checkpoint, saved conversation, extracted CSV attachment, two Neo4j notes and relationship survive encrypted export/import and restoration |
| Neo4j migration | 5.26.31 → 5.26.32 persistence, auth, scope filtering, uniqueness, restart and logical rollback pass |
| LiteLLM migration | Restricted key survives migration/restart; unauthorized access and external alias rejected; real local streaming/embedding and logical rollback pass |
| Control lifecycle | 301.48 seconds, 133 cycles, 1,265 HTTP requests, read p95 27.71 ms, SQLite integrity OK; continuous measured worker |
| Critical browser journeys | 12 pass across Chromium desktop/mobile, Firefox and WebKit Linux |
| Grafana | 13 signed plugins accepted, six EN/FR dashboards, 102 rendered panels, real Prometheus query/Tempo trace, no browser JS exception |
| Host service restrictions | Synthetic document extraction and age availability pass with NoNewPrivileges, PrivateTmp, ProtectSystem and private umask |

The five-minute lifecycle exercise is not a 24-hour soak or a measurement of GPU
capacity. Browser tests do not certify physical microphone/speaker behavior or
all Safari/iOS versions. Model contract passes do not establish incident diagnosis
quality; observed counterexamples informed structural fixes and consulted holdout
cases were explicitly moved into regression.

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

## Remaining acceptance boundaries

- A fresh exact-commit CI result and complete final qualification are required
  before publication; working-tree tests are development evidence.
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
