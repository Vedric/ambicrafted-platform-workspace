# ADR 0042 — Minimal Grafana distribution with bounded private signatures

Date: 2026-10-21

Status: accepted for candidate qualification; promotion is separate.

Supersedes the affected implementation choice in ADR 0036. Historical findings
and the unchanged CRITICAL/HIGH release gate remain part of the record.

## Context

Rebuilding Grafana's core fixed its affected OpenAPI dependency, but 56 HIGH
findings remained in the official signed datasource executables. Rechecking the
current official catalogs did not find corrected archives. Ordinary modification
of a signed plugin invalidates its signature; an unsigned-plugin exception would
weaken a real trust boundary. The requirement is corrected software with honest
provenance and enforced verification, not a lower scanner count by omission.

An authenticated read-only inventory of the actual instance, including stored
datasources, dashboards and alert rules, found only Prometheus and Tempo use:
four datasource records of those types, six dashboards, 102 content panels using
builtin panel types, and no alert rules. Maintaining all thirteen bundled external
datasources would add unnecessary build/signing/compatibility work for this
private platform.

## Decision

Ship only rebuilt Prometheus and Tempo plugins, retaining their existing IDs and
official frontend assets. Explicitly remove the eleven unused datasource plugins
and disable automatic preinstallation/update. This reduces available integrations;
a future integration requires inventory review and a separately qualified build.

Build both backends from their pinned official source revisions, using Go 1.27.3,
locked corrected dependencies and the upstream Mage SDK build path. Preserve the
complete patched backend sources, licenses and provenance in each signed bundle.
The final Docker build has no signing key and refuses any artifact that does not
match the committed signed inventory byte for byte.

Use a private offline RSA3072 authority expressly labelled "Ambicrafted local
distribution", not Grafana Labs. Compile its exact public fingerprint, the two
plugin IDs/versions and the SHA-256 of each complete armored manifest into the
Grafana core. Verify the signature with maintained ProtonMail OpenPGP code.
Preserve upstream validation of ID, version, all file checksums, missing/extra
files and exact private root URLs. Official Grafana-key verification is unchanged.
No unsigned-plugin exception, configurable trust root, network retrieval fallback
or loader-status bypass is added. Only localhost:3000 and 127.0.0.1:3000 root URLs
are signed; changing the deployment's root URL requires a reviewed new release.

The Tempo datasource needs protobuf messages, not the Tempo server. Copy the
exact 23 protocol files from official Tempo 3.1.0 into an internal package,
changing import prefixes only. Record every original/derived file hash, the
upstream source commit, licenses and an ordinary SPDX source component. The build
rejects an imported `github.com/grafana/tempo/` package. The 3.1 contract is needed
because 3.0.3 lacks the QueryRangeResponse.Step field expected by this plugin.
This explicitly changes the source dependency structure; it does not fabricate
a corrected Go module version or remove an inventory entry for unchanged code.

Also apply the genuine zlib runtime security update. Preserve the residual
UNKNOWN x/crypto advisory: it concerns the unmaintained openpgp package, while
the build rejects that package in the executable's actual OSS package closure
and uses maintained ProtonMail code. Keep the complete closure as an artifact.

## Alternatives rejected

- Waiting without examining alternatives leaves necessary plugins affected when
  no corrected official catalog package exists. Reconsider official packages
  at each maintenance cycle, because they would reduce private-fork upkeep.
- Removing optional plugins alone leaves both necessary plugins vulnerable.
- Disabling signature verification, allowing unsigned plugins or editing binary
  metadata/SBOM versions would conceal or weaken the boundary and is rejected.
- An unbounded custom public key would allow that key to authorize arbitrary
  plugins; whole-manifest, ID and version pins deliberately prevent this.
- Official Grafana private signing requires a Cloud organization/token and
  compatible organization-prefixed IDs, which are not available here and would
  require datasource/dashboard migration. It remains a future alternative.
- Rebuilding all thirteen plugins adds maintenance and regression surface without
  preserving a currently used feature. Actual database inventory, not only
  provisioning files, justified the two-plugin scope.

## Consequences and evidence

The private key stays outside the checkout/build context in operator-owned
0700/0600 state. Public manifests are sufficient for repeat builds. Key backup
must be encrypted and tested off-host; this change does not claim that backup
exists. Rotate before its two-year expiry or after suspected compromise by
reviewing a new public fingerprint, signing reviewed artifacts and rebuilding the
core pins. A compromised key alone cannot create different accepted manifest
bytes under an unchanged core, but key/core supply-chain protection still matters.

Candidate qualification observed genuine upstream race tests, protocol tests,
official signature/loader regression tests, actual reader and bundle validation,
and real Grafana refusal of altered binaries, changed manifests, missing/extra
files, foreign key IDs, unsigned plugins and wrong root URLs. The intact plugin
remained usable where applicable. Six dashboards/102 content panels rendered in
Chromium; Prometheus and Tempo traceId/TraceQL returned synthetic telemetry.
The host-prepared artifacts reproduced byte for byte inside the Docker build.
The complete candidate scan has zero CRITICAL/HIGH/MEDIUM/LOW, retaining the one
UNKNOWN finding. These checks are neither the complete Grafana upstream suite
nor a claim of absence of unknown vulnerabilities.

This distribution is Linux/amd64 and maintains a narrow core verification patch.
Every changed plugin manifest requires a core rebuild, fresh negative tests,
functional qualification and scan. The existing database remains a separate
backup/rollback concern. AGPL, protocol license notices and corresponding source
obligations remain; a future commercial distribution must preserve them.
Implementation, public pins and reproducible commands live in
`gateway/images/grafana/README.md`.
