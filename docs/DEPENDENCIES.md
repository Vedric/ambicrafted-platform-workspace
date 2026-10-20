# Dependency review

The current candidate inventory and remaining release gates are documented in
[the 21 October candidate qualification](QUALIFICATION-2026-10-21.md). The latest
eight-image development scan reports zero CRITICAL/HIGH, with 42 MEDIUM,
12 LOW and six UNKNOWN package/advisory occurrences still visible. Grafana's
plugin and Qdrant's frontend corrections are qualified separately; the release
gate still rejects any CRITICAL/HIGH or incomplete scan against the final
artifacts. This development result does not establish live deployment or hosted
release acceptance. Application Python and npm audits are separate image-scan
inputs, not substitutes for those scans.
The [29 September assessment](SECURITY-2026-09-29.md),
[27 September review](SECURITY-REFINEMENT-2026-09-27.md) and figures below are
historical snapshots, not the current image inventory.

The initial six-image review used two narrow derivatives, PostgreSQL and Qdrant.
The current candidate has eight declared derivatives with pinned upstream
inputs and explicit corrective changes. Their image-specific READMEs and
ADRs 0035–0037 and [ADR 0042](adr/0042-distribution-grafana-privee-corrigee.md) describe the builds and the private Grafana distribution. [ADR 0044](adr/0044-retrait-cible-racine-emsign-g3.md)
records the subsequent exact CA distrust, certifi 2026.10.19 and Pillow 13.0.0
corrections. [ADR 0012](adr/0012-images-correctives-verifiees.md)
records the initial decision.

## Historical image inventory — 2026-09-26

Trivy 0.74.0 with the vulnerability database updated on 2026-09-26 12:58 UTC
reports the following package occurrences. The same advisory can occur in
several binaries; these are not counts of proven exploitation paths.

| Image in service | Critical | High | Medium | Low | Unknown |
|---|---:|---:|---:|---:|---:|
| LiteLLM 1.102.1 | 0 | 0 | 9 | 0 | 0 |
| PostgreSQL 16.15, corrected gosu 1.19 / Go 1.27.1 | 0 | 0 | 0 | 0 | 1 |
| Tempo 3.0.3 | 0 | 12 | 4 | 4 | 2 |
| Prometheus 3.15.0 | 0 | 0 | 0 | 0 | 2 |
| Grafana 13.2.2 | 0 | 104 | 33 | 35 | 6 |
| Qdrant 1.19.1, corrected Perl package | 0 | 50 | 63 | 59 | 2 |
| **Total** | **0** | **166** | **109** | **98** | **13** |

The tested derivatives remove all four critical and 25 high occurrences from
the updated upstream baseline (4 critical / 191 high). PostgreSQL's helper was
rebuilt from the same official source commit; Qdrant receives a signed Debian
backport. The original pre-upgrade stack had 7 critical / 363 high occurrences.
Counts compare the evidence snapshots, not an exhaustive vulnerability history.

The remaining Tempo/Grafana findings include embedded Go runtimes and libraries;
OS package updates alone do not replace those binaries. Qdrant includes
unfixed distribution advisories and further available package corrections.
The full [release security assessment](SECURITY-RELEASE-2026-09-26.md) records
primary advisories, exact artifacts, applicability limits, remediation priorities
and scan provenance. All findings remain visible; no scanner suppression or
blanket risk waiver was added. That historical review requested reassessment by
2026-10-10; the current reassessment is recorded in
[the 21 October qualification](QUALIFICATION-2026-10-21.md). Repeat scans after
each image change and before release.

Loopback bindings, authenticated console, private files and
`no-new-privileges:true` reduce exposure. They do not fix vulnerable image
contents. Supervised use by one trusted workstation operator is the qualified
scope. Unconditional production security sign-off and remote multi-user
publication remain blocked by the documented remediation and architecture work.

## Application dependencies and automation

All four Python projects use committed uv locks. CI audits their runtime
requirements with pip-audit 2.10.1; local package sources are excluded from the
public dependency lookup. Standalone maintenance scripts have their own locks.
React/Vite and evaluation-fixture validation use npm locks, Node 22.23.3 and
npm 11.10.0. Promptfoo was removed from the supported installation on 20 October;
the real Python graph/MCP qualification replaces it, and external-provider
comparison is no longer a supported npm command. The four Python audits and both
npm audits reported zero known advisories after the targeted corrections.
This does not cover the container findings above or unknown vulnerabilities.

Dependabot watches GitHub Actions, npm, uv, Compose upstream images and all eight
corrective Dockerfiles. Dated local image tags are excluded from registry update
lookups; changes require a rebuild and qualification. The separate manual/weekly
image-security workflow retains full reports and fails on critical/high findings.
Functional CI passing is therefore not a container security sign-off. Tagged
releases reuse both workflows and create a draft only when both pass. Complete
image reports include identity and bounded, redacted preparation failure
diagnostics. No existing report is reused after a failed scan.

Source rebuilds can exceed a hosted runner's initial free disk space. For the
Grafana, Prometheus and Tempo jobs only, the workflow verifies that it is on a
disposable GitHub-hosted Linux runner, removes four unused preinstalled SDK
directories, records disk capacity and requires at least 25 GiB free before
building. It does not clean Docker resources or apply this preparation to a
workstation or self-hosted runner. A resource failure still fails qualification.

## Historical evaluation dependency correction — 2026-09-29

This section describes the former Promptfoo tree. Those dependencies and their
regression tests were removed with Promptfoo on 20 October; the present npm
evaluation package contains only the pinned YAML fixture parser.

During console release qualification, npm audit reported three vulnerable
transitive packages in `evals` (one high, two moderate). Exact overrides and the
lock now select the compatible corrective releases below; other dependency
versions are retained. The application gateway/provider aliases are unchanged.

| Package | Previous → corrected | Official advisories |
| --- | --- | --- |
| fast-uri | 3.1.6 → 3.1.7 | [Port authority injection](https://github.com/advisories/GHSA-qw65-cvwx-89v3), [bracket host confusion](https://github.com/advisories/GHSA-58mr-gqgx-xq4g) |
| ip-address | 10.5.0 → 10.5.1 | [Link-local classification](https://github.com/advisories/GHSA-rpw4-54j3-4h4q), [local-use NAT64 classification](https://github.com/advisories/GHSA-2vr4-cq9g-pvrc) |
| undici (6.x SDK dependency) | 6.28.0 → 6.28.1 | [WebSocket decompression denial of service](https://github.com/advisories/GHSA-3wwx-pv8p-q78v) |

The 6.x-only undici override does not downgrade the separately installed 7.x/8.x
branches. `npm ci --ignore-scripts`, configuration/security tests and
`npm audit --audit-level=moderate` validate the locked tree. Pure local regression
cases exercise authority injection rejection and IPv6 classifications; they send
no network traffic. The advisory fixes do not constitute a proof that every
consumer applies SSRF policy correctly, or remediate the container findings above.

Historical image reports and checksums are outside Git at
`/home/vedric/platform/finalisation-2026-09-26/console/security/`.

## Historical application update — 2026-09-27

The console and control plane are version 0.3.0; the speech runtime is version
0.2.0. The immersive bilingual interface adds no application dependency. Translation
is explicit and local; Markdown is loaded in a separate chunk. The additional
English speech weights have a pinned revision, size, checksum and license in
[the voice manifest and guide](VOICE.md). French and long English recordings
retain the multilingual transcription model. Short English turns additionally
use a dedicated pinned model, adding approximately 1.53 GB of model files and
increasing CPU/memory cost without a new package or cloud service. The exact
sample-count boundary and observed recognition tradeoffs are recorded in
[ADR 0021](adr/0021-reconnaissance-anglaise-dediee.md).

The image set above has not changed in this application release; its dated findings
remain open. Application dependency audit results and final-commit verification
are recorded separately in [the current release review](RELEASE-2026-09-27.md).

The subsequent [coordinated dependency maintenance](DEPENDENCY-UPDATES-2026-09-27.md)
updates the application toolchain to Node 22.23.3, jsdom 30.1.1, coherent
MCP/Pydantic/LangGraph locks and pinned build/lint tools. The earlier snapshot
above remains historical. PostgreSQL major upgrades require a separately
qualified data migration under [ADR 0016](adr/0016-maintenance-dependances-et-postgresql.md).
