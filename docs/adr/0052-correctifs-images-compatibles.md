# ADR 0052 — Qualify compatible fixes beyond the blocking image threshold

Date: 2026-10-22

Status: Accepted for the personal workstation image profile.

## Context

The complete image scan blocks CRITICAL and HIGH findings. That threshold alone
left released fixes for lower-severity dependencies unapplied. Fresh Python
audits also rejected a PDF dependency that the image threshold did not block.
The requested release needs an explicit disposition of available fixes and
runtime compatibility evidence, not a green threshold presented as universal
security.

## Decision

Prefer supported releases within the installed application branches. Keep exact
upstream artifacts, checksums, package records and licenses. Install native OS
packages through their authenticated distribution mechanism. Use offline
installation only after signature/index verification and hash checks; do not
use an untrusted-package override.

Apply the compatible Wolfi libc update in LiteLLM, Alpine musl/zlib fixes in
PostgreSQL and musl fixes in Grafana. Rebuild gosu from its unchanged official
release with the two affected Go modules corrected. Keep the PostgreSQL server,
Grafana executable/plugins and LiteLLM application files unchanged, and compare
the actual installed bytes to prove that boundary.

Align Neo4j's installed JLine family with the security-fixed 3.30.15 release and
its declared native/Jansi dependencies. Exercise the real history matcher,
administrative commands, authenticated graph operations and recovery. Retain the
vendor's Neo4j LTS branch. Its remaining scanner record for CVE-2026-1337 is kept
visible alongside the vendor's explicit 5.26.31 backport notice.

For Qdrant, rebuild the pinned 1.19.2 server source with three compatible Cargo
lock corrections: rand 0.8.6/0.9.3 and xxhash-rust 0.8.16. Preserve upstream
release LTO, generic x86_64 CPU mode and the stacktrace feature. Regenerate the
Rust SPDX with the pinned cargo-sbom tool from that actual source graph.
The measured build and dependency/storage tests justify this bounded source
recipe; no Rust source fork or GPU/ARM support claim is introduced. The final
r4 Docker command took 14 minutes 52.8 seconds. The measured Rust compiler
cgroup peak was 8.8203 GiB including file cache. The Rust stages compiled from
source while unchanged dashboard, healthcheck and trust-helper stages used
cache; this is not a fully uncached build or a hosted-runner duration guarantee.
The image workflow requires at least 12 GiB RAM and 25 GiB free disk for this
build, with a 45-minute build limit inside its 60-minute job.

The r4 runtime passes synthetic migration, search, persistence, snapshot recovery
and three Chromium dashboard views under Docker's default seccomp policy, with
dropped capabilities and a read-only root filesystem. Separate upstream
persisted-hashmap tests exercise io_uring unconditionally and needed a temporary
test-only profile adding those three syscalls. Their initial default-seccomp
failures remain recorded; that extension is not the deployed runtime policy.

Update the complete Qdrant web dashboard and its generated dependency
inventory together. Replace the complete Debian CA package material, including
obsolete aliases, rather than overlaying files that leave removed anchors
trusted. Apply the exact Comodo AAA distrust to Prometheus and the metrics
exporter, whose native stores still contained that anchor. Preserve every
unrelated root and the build helper's original default behavior.

Qualify each changed image with its actual identity, full scan and relevant
startup, access-control, persistence and restore behavior. The application
freeze and the image revisions are separately identifiable. The release's
hosted workflow still rebuilds and audits all eight images with current scanner
data; local results do not substitute for that gate.

## Alternatives rejected

- Ignoring all MEDIUM/LOW findings merely because they pass the release threshold.
- Hiding vulnerable package metadata, rewriting an SBOM without its binaries,
  ignoring unfixed findings, or disabling signature checks to force installation.
- Migrating Neo4j to a different major release solely to satisfy a scanner's
  incomplete version matching despite the documented LTS backport.
- Rebuilding the whole deployment model or adding a shared workstation CI runner
  to resolve a bounded dependency issue.

## Consequences

The derivative recipes remain a maintenance responsibility. A new upstream
artifact or dependency graph must fail a stale pin and be requalified, not be
silently accepted. Residual findings without a qualified available fix remain
listed with their scope; there is no zero-vulnerability claim. Historical scans
and rejected experiments are preserved. Same-version application updates still
require a recoverable baseline and a controlled local promotion.

The final eight local images report 0 CRITICAL, 0 HIGH, 23 MEDIUM, 9 LOW and
5 UNKNOWN occurrences with the 22 October 07:10:52 UTC Trivy database. Qdrant r4
accounts for 23 MEDIUM/8 LOW, Neo4j for one LOW, and the Go module inventory
records in Grafana, Prometheus, the metrics exporter and Tempo for five UNKNOWN.
The [qualification](../QUALIFICATION-2026-10-22.md#security-snapshot) records
the exact local identities. These counts establish neither completed hosted
gates nor a successful live promotion or a vulnerability-free deployment.

References: [JLine advisory](https://github.com/jline/jline3/security/advisories/GHSA-5q95-hrpc-m3w3),
[Neo4j backport](https://neo4j.com/release-notes/database/neo4j-5-26-31/),
[Debian trust update](https://www.debian.org/security/2026/dsa-6572).
