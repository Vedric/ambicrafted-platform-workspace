# Qdrant security derivatives

Two build targets preserve the Qdrant 1.19.1 executable at the tested upstream
image digest. Both rebuild Web UI 0.2.15 from its pinned source commit, a committed
npm lockfile and an explicit, reviewable patch. Neither build promotes itself.

The default target retains the upstream operating-system image and entrypoint,
with signed Debian security backports for Perl, gzip, glibc, PCRE2 and SQLite.
The `minimal` target is a separate nonroot, shell-free Debian 13 runtime. Consult
the qualification report before selecting it: existing storage ownership and
the healthcheck need a controlled migration.

```sh
# Conservative candidate: preserves the upstream entrypoint.
docker build --pull=false \
  --tag ambicrafted/qdrant:1.19.1-security.20260927 \
  gateway/images/qdrant

# Separate minimal candidate; does not replace the preceding image.
docker build --pull=false --target minimal \
  --tag ambicrafted/qdrant:1.19.1-security.20260927-minimal \
  gateway/images/qdrant
```

Use only this directory as the build context. `.dockerignore` explicitly permits
the build recipe, npm manifests/lock, source patch and healthcheck source/tests.
It excludes private configuration, backups and the rest of the repository.
Upstream archives and image references are pinned by checksum/digest; npm checks
locked package integrity. APT preserves Debian signature verification and exact
security package versions. An unavailable pinned input must fail the build.

The dashboard dependency update includes `js-yaml` 4.3.2, Vitest 4.1.11 and React
Router 7.18.4. Other security updates in the lockfile are recorded in the private
qualification evidence. The small source patch avoids an invalid link when a
card has no destination and disables automatic cloud metadata/release-banner
requests in this private build. Missing cloud data remains `null`; no health,
version or availability data is fabricated. Documentation links remain usable
when an operator chooses to follow them.

The build runs the complete upstream dashboard suite plus its offline-metadata
regression test, compiles the actual static assets and regenerates the complete
npm SPDX inventory, including development dependencies. The unchanged Rust SPDX
inventory remains next to the unchanged server binary. The minimal image keeps
Debian package records, original checksums and copyright notices for its copied
native libraries. Its bounded HTTP healthcheck is built and tested with pinned
Go 1.27.1, with build information preserved for scanners.

The minimal runtime uses UID/GID 65532, `RUN_MODE=production` and UTC, with an
explicit init-marker path inside storage. It starts Qdrant directly. Consequently
it does **not** implement the upstream shell wrapper's optional
`QDRANT_ALLOW_RECOVERY_MODE` automatic recovery after an OOM during startup.
Ordinary SIGTERM and container restart persistence are qualified separately.
Do not enable that optional wrapper feature for this target.

Before promotion, create and restore a backup, stop the old service, and migrate
only its dedicated storage to UID/GID 65532. Replace shell healthchecks with
`["CMD", "/qdrant/healthcheck"]`. A read-only root filesystem also needs writable
`/tmp` and `/qdrant/snapshots`, or an explicit snapshot directory inside the
persistent storage mount. Size writable mounts for the real corpus; the small
test limits are not production capacity recommendations. Preserve loopback-only
publication, `no-new-privileges` and dropped capabilities. Never mount the Docker
socket or use privileged/host namespace modes.

These dated tags are local build outputs, not published registry digests.
Another host must rebuild and qualify the resulting image or consume an approved
publication with its registry digest. Local image IDs, exact scan counts,
provenance, remaining advisories and the successful disposable data/browser
checks are in the [2026-09-27 security refinement report](../../../docs/SECURITY-REFINEMENT-2026-09-27.md).
The [2026-09-26 assessment](../../../docs/SECURITY-RELEASE-2026-09-26.md) remains the
historical baseline; its findings must not be silently relabelled as this build.
