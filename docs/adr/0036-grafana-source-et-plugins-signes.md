# 0036 — Grafana source rebuild with intact signed plugins

Date: 2026-10-20

Status: Accepted for the qualified candidate; release security gate remains open.

## Context

The official Grafana 13.2.4 image scanned on this date has 61 HIGH package/CVE
occurrences. Five are in the backend's `kin-openapi` module. The other 56 are in
the thirteen bundled datasource executables, including Prometheus and Tempo,
which this platform uses. The latest official catalog archives do not remove
those plugin findings. A scanner result alone does not establish reachability
of every vulnerable function, but no reviewed non-applicability evidence exists
that would justify dismissing them.

Grafana authenticates plugin content through its signed manifest. Recompiling
and replacing a plugin binary invalidates that signature. Accepting unsigned
plugins globally, modifying version metadata, or hiding findings would weaken
the platform's existing security contract.

## Decision

Rebuild the Grafana OSS backend from the exact 13.2.4 source commit with the pinned
Go 1.27.3 compiler image and `kin-openapi` 0.149.0. Record and check the source
archive and resultant dependency-file hashes. Keep a readable dependency patch
and mark the executable as the platform's derivative.

Retain all thirteen bundled plugins. Replace only OpenTSDB and Google Cloud
Monitoring with their newer, complete official signed archives, pinned by hash.
The other eleven are already at the audited catalog versions in the 13.2.4 base.
Never alter a plugin's files or manifest after download.

Qualify the candidate against disposable, internal-network Prometheus/Tempo
fixtures and the repository's actual provisioning files. Verify authentication,
plugin signatures, datasource queries, dashboard provisioning and browser
rendering. Do not load live volumes or production credentials.

Keep every residual finding in the security report and keep the release gate
failing on CRITICAL/HIGH. This decision improves the candidate; it does not
authorize describing it as free of vulnerabilities.

## Alternatives rejected

- Keep the official backend unchanged: it leaves five fixable HIGH findings.
- Replace the whole release or every plugin speculatively: current official
  versions were inspected first, and newer signed archives still retain the
  relevant findings.
- Locally rebuild signed datasource binaries in place: this invalidates the
  publisher's signature. A differently named, maintained internal plugin would
  require its own trust, distribution and compatibility design.
- Remove all optional plugins: it cannot fix the two required datasources and
  can change supported behavior or trigger automatic preinstallation. Revisit
  deliberate plugin reduction separately, with installation controls and tests.
- Edit Go build metadata, add scanner ignores, or assert that unused dependency
  code is safe without evidence: none corrects a vulnerable implementation.

## Consequences and evidence

The actual derivative build passes three targeted upstream test packages:
Grafana alert-rule validation, `kin-openapi/openapi3`, and
`kin-openapi/openapi3filter`. Short mode excludes the upstream remote APIs.guru
corpus; it does not certify all Grafana subsystems.

The built candidate's scan reports 0 CRITICAL, 56 HIGH, 173 MEDIUM, 13 LOW and
5 UNKNOWN occurrences. The five backend HIGH findings are removed by an actual
source rebuild. The remaining HIGH findings belong to the signed plugin binaries.

The disposable runtime checks verify all thirteen signatures as valid, six
provisioned dashboards and real queries through both required datasource
backends. The browser qualification captures EN/FR rendering using synthetic
telemetry; missing application-specific series are not replaced with fictitious
production values.

This adds compiler downloads, build time, source-provenance maintenance and a
narrow upstream patch to every release. The derivative is limited to the
qualified Linux/amd64 target. Plugin security fixes still depend on a trustworthy
signed upstream release or a new reviewed design; the release blocker remains
visible. A public or commercial production claim must wait for that resolution
and the other independent release gates.

The reproducible build and qualification procedure lives in
[`gateway/images/grafana/README.md`](../../gateway/images/grafana/README.md).
