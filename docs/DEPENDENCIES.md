# Dependency review

The current seven-image inventory and promoted derivatives are documented in
[the 27 September refinement](SECURITY-REFINEMENT-2026-09-27.md): 0 CRITICAL,
53 HIGH. Current application versions: console 0.4.4, control API 0.4.1,
speech runtime 0.3.1.
The HIGH/CRITICAL gate remains failed; the older figures below are historical.

Six production image versions were pinned in the initial review. PostgreSQL and Qdrant are narrow
local derivatives with immutable upstream bases and exact corrective versions;
other services use upstream registry digests. Their dedicated build contexts
exclude environment files and data. See [ADR 0012](adr/0012-images-correctives-verifiees.md).

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
blanket risk waiver was added. Review again after every image change and no
later than **2026-10-10**.

Loopback bindings, authenticated console, private files and
`no-new-privileges:true` reduce exposure. They do not fix vulnerable image
contents. Supervised use by one trusted workstation operator is the qualified
scope. Unconditional production security sign-off and remote multi-user
publication remain blocked by the documented remediation and architecture work.

## Application dependencies and automation

All four Python projects use committed uv locks. CI audits their runtime
requirements with pip-audit 2.10.1; local package sources are excluded from the
public dependency lookup. Standalone maintenance scripts have their own locks.
React/Vite and promptfoo use npm locks, Node 22.23.3 and npm 11.10.0. The verified
runtime Python and npm audits reported zero known advisories at this snapshot.
This does not cover the container findings above or unknown vulnerabilities.

Dependabot watches GitHub Actions, npm, uv, Compose upstream images and the two
corrective Dockerfiles. Dated local image tags are excluded from registry update
lookups; changes require a rebuild and qualification. The separate manual/weekly
image-security workflow retains full reports and fails on critical/high findings.
Functional CI passing is therefore not a container security sign-off.

## Evaluation dependency correction — 2026-09-29

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

## Application update — 2026-09-27

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
