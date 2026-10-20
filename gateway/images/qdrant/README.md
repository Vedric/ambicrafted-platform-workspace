# Qdrant security derivatives

Two build targets preserve the Qdrant 1.19.2 executable at its pinned upstream
image digest. Both rebuild Web UI 0.2.15 from its pinned source commit, a committed
npm lockfile and an explicit, reviewable patch. Neither build promotes itself.

The **default final target is the nonroot, shell-free Debian 13 runtime**.
`apt-ui` is an explicit comparison target retaining the upstream operating-system
image and entrypoint with signed Debian security backports. Existing storage
ownership and the healthcheck still need a controlled migration when replacing
an older root-based deployment.

```sh
# Qualified minimal runtime (the default).
docker buildx build --load \
  --tag ambicrafted/qdrant:1.19.2-security.20261020 \
  gateway/images/qdrant

# Separate comparison image retaining the upstream shell entrypoint.
docker buildx build --load --target apt-ui \
  --tag ambicrafted/qdrant:1.19.2-security.20261020-apt \
  gateway/images/qdrant
```

Use only this directory as the build context. `.dockerignore` explicitly permits
the build recipe, npm manifests/lock, source patch and healthcheck source/tests.
It excludes private configuration, backups and the rest of the repository.
Upstream archives and image references are pinned by checksum/digest; npm checks
locked package integrity. APT preserves Debian signature verification and exact
security package versions. An unavailable pinned input must fail the build.

The dashboard dependency update includes `js-yaml` 4.3.2, Vitest 4.1.11, React
Router 7.18.4 and the subsequently patched `source-map-js` dependency. Consult
the committed lockfile and build evidence for their exact resolved versions.
The small source patch avoids an invalid link when a
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
Go 1.27.3, with build information preserved for scanners.

The complete build-dependency SBOM still contains a **HIGH finding in
`braces` 3.0.3** without a fixed release in the qualification database.
That is a build dependency recorded in the shipped inventory, not evidence
that the browser executes that package. It remains reported without suppression:
do not claim a clean CRITICAL/HIGH release gate or remove the inventory to obtain
one. The `source-map-js` correction was rebuilt into the actual dashboard and
its regenerated SBOM; no version metadata was edited in place.

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

## Synthetic upgrade and recovery qualification

With the locked control API dependencies installed and a local Linux Docker
Engine, run:

```sh
uv run --project apps/control-api --no-sync python \
  gateway/images/qdrant/qualifier.py \
  --old-image ambicrafted/qdrant:1.19.1-security.20260927 \
  --new-image ambicrafted/qdrant:1.19.2-security.20261020 \
  --output /absolute/path/to/new-qdrant-evidence
```

The test creates only unique synthetic volumes and an internal network. It uses
private bridge addresses without publishing or reserving host ports. The pinned
official Qdrant image acts only as a short-lived ownership helper on these
synthetic volumes; it never mounts live state.

The fixture exercises vector ranking, payload filtering/indexes, alias continuity,
existing-volume upgrade, post-upgrade writes/deletion and restart persistence.
It creates a pre-upgrade collection snapshot and a post-upgrade snapshot, restores
both into a fresh candidate volume, and restores the **pre-upgrade** snapshot into
a separate old-version volume. This rollback never opens upgraded storage with
the old binary. Collection snapshots do not contain aliases; the test checks their
absence and explicitly recreates the intended alias after recovery.

The runtime healthcheck and dashboard HTML are checked. This is not a browser,
load, production-corpus or distributed-cluster test. Snapshot files, logs and
`qualification.json` contain only synthetic fixture data. Every created container,
volume and network is removed; a cleanup failure fails the qualification.

## Historical evidence

These dated tags are local build outputs, not published registry digests.
Another host must rebuild and qualify the resulting image or consume an approved
publication with its registry digest. Local image IDs, exact scan counts,
provenance, remaining advisories and the successful disposable data/browser
checks for the **previous 1.19.1 derivative** are in the
[2026-09-27 security refinement report](../../../docs/SECURITY-REFINEMENT-2026-09-27.md).
The [2026-09-26 assessment](../../../docs/SECURITY-RELEASE-2026-09-26.md) remains the
historical baseline; its findings must not be silently relabelled as this build.
