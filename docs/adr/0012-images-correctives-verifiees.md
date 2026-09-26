# ADR 0012: verified corrective container derivatives

Date: 2026-09-26. Status: accepted.

## Context

The latest tested upstream images still contain known vulnerabilities. Qdrant
has three critical package occurrences with an available signed Debian update.
PostgreSQL's only critical occurrence is in the Go runtime embedded in its gosu
startup helper. A package update does not replace that embedded runtime.

## Decision

Maintain two narrow local derivatives. Each Dockerfile starts from the exact
tested upstream digest and has a dedicated context that permits only the
Dockerfile and its ignore file. Qdrant upgrades the exact `perl-base` version.
PostgreSQL rebuilds the same official gosu commit with a checksum-verified,
patched Go compiler and unchanged dependency sums. Two gosu compilations are
compared; build tools are absent from the final image.

Compose declares dated local tags and their build contexts. Another host must
build the derivatives with `docker compose up -d --build` and qualify the
result; these tags are not published registry artifacts. The tested local IDs
and exact versions are recorded with the build instructions. Every package or
compiler change requires a new dated tag, scan and functional qualification.
Unavailable pinned artifacts cause a build failure rather than an unpinned
fallback. All six services also declare `no-new-privileges:true`.

Promotion follows a private backup and disposable restore drill, then recreates
containers while preserving named volumes. Health, application paths and a
new restore drill verify the promoted versions. The release security report
keeps all unresolved findings visible and separates upstream baseline from
the running derivatives.

## Verified behavior

The Qdrant candidate restored 31 vectors, queried and wrote data, and preserved
new data across restart. PostgreSQL initialized twice, dropped to UID 70,
restored 86 tables, persisted 250 writes across restart, and dumped/restored
again. Neither test touched production volumes. Their scans remove all four
critical occurrences and 25 high occurrences from the upstream aggregate.

## Alternatives rejected

Scanner suppressions without reachability evidence, arbitrary package removals,
unversioned upgrades and wholesale application forks were rejected. Updating
Go in the runtime filesystem would leave the old gosu binary unchanged.

## Consequences

We own rebuilding and maintaining these small derivatives. Exact artifacts and
signed package repositories must remain available; clean builds require network
access. PostgreSQL's derivative is qualified only for Linux amd64. Image build
metadata may change the final image ID even when a binary rebuild is identical.
Remaining high-severity findings still prevent an unconditional security sign-off.
`no-new-privileges` is an additional boundary, not a substitute for patching,
non-root/capability qualification or host hardening.

See [release security assessment](../SECURITY-RELEASE-2026-09-26.md) and
[operational recovery](../OPERATIONS.md).
