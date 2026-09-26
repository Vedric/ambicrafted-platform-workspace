# Dependency review — 2026-09-26

Six production image versions are pinned. PostgreSQL and Qdrant are narrow
local derivatives with immutable upstream bases and exact corrective versions;
other services use upstream registry digests. Their dedicated build contexts
exclude environment files and data. See [ADR 0012](adr/0012-images-correctives-verifiees.md).

## Final image inventory

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
React/Vite and promptfoo use npm locks, Node 22.22.0 and npm 11.10.0. The verified
runtime Python and npm audits reported zero known advisories at this snapshot.
This does not cover the container findings above or unknown vulnerabilities.

Dependabot watches GitHub Actions, npm, uv, Compose upstream images and the two
corrective Dockerfiles. Dated local image tags are excluded from registry update
lookups; changes require a rebuild and qualification. The separate manual/weekly
image-security workflow retains full reports and fails on critical/high findings.
Functional CI passing is therefore not a container security sign-off.

Image reports and checksums are outside Git at
`/home/vedric/platform/finalisation-2026-09-26/console/security/`.
