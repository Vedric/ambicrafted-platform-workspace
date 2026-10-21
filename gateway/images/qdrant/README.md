# Qdrant security derivatives

## Dashboard build-tool correction — 2026-10-21, r2

The `1.19.2-security.20261021-r2` derivative pins the actual dashboard build
dependency to **Vite 6.4.4**, replacing locked 6.4.3. No other resolved npm
package changes. The upstream [file-existence bypass advisory](https://github.com/vitejs/launch-editor/security/advisories/GHSA-587h-7wmj-h5pm)
(CVE-2026-112942, HIGH) identifies 6.4.4 as the corrected Vite 6 version. It
includes the corrected bundled `launch-editor` path resolution and Windows
command handling, also addressing the related percent-expansion flaw.

The official tarball integrity is committed in `web-ui-package-lock.json`.
The dashboard is rebuilt and its complete npm SPDX inventory is regenerated;
the dependency is not removed from the inventory. The Rust server, upstream
sources, runtime libraries, trust policy and image bases remain unchanged.
The previous dated image/tag is retained for controlled recovery.

The advisory concerns a Windows development-server editor launcher. This
Linux/WSL image serves static browser assets and contains no Node runtime;
that exposure limit does not exempt its build dependencies from the blocking
image-security gate. The existing offline dependency checks, all 167 upstream
dashboard tests and production build run again for this patch. Synthetic
browser, search, persistence and snapshot recovery checks qualify the resulting
image separately; no live service is modified by a build or qualification.
The earlier scan below is historical: the refreshed hosted database detected
the HIGH in 6.4.3, so that old result is not evidence for the corrected image.

The local r2 build passed the 167 dashboard tests and six dependency checks,
then passed the disposable upgrade/restart/search/snapshot-recovery fixture and
three real Chromium dashboard views, with no external requests, JavaScript errors
or cleanup failures. Its rebuilt browser assets are byte-identical to the prior
image; only the generated dashboard SPDX changes in the static directory. The
server binary, Rust SPDX and CA-policy report are also byte-identical. This does
not imply that the vulnerable build tool was merely renamed: the build log records
the execution of Vite 6.4.4 from the corrected lock.

One local scan using Trivy 0.74.0 and a freshly downloaded database updated
2026-10-21 at 01:19:53 UTC reports **0 CRITICAL, 0 HIGH, 23 MEDIUM, 11 LOW and
1 UNKNOWN**. The database SHA-256 is
`50b0d49617d6efa3a1883b1f84b07c321c7f31bc1a4cda43575df3093fc6f897`, identical
to the hosted database that detected the older image's HIGH. The UNKNOWN is
`DSA-6572-1` against the unchanged vendor `ca-certificates` package; the exact
compromised root was separately removed by the existing trust policy, with no
package-version rewriting or advisory suppression. These are local candidate
results, not a hosted pass or a live deployment claim.

## Targeted trust correction — 2026-10-21

The current dated image additionally distrusts the exact compromised emSign ECC
G3 root in its actual operating-system trust stores. See the shared
[trust policy](../trust-policy/README.md) for the fingerprint, native Java handling,
unchanged package inventory, qualification evidence and limits. This is a local
trust-policy change, not a claim that the vendor CA package was upgraded.
The named build context below contains only public policy code and certificates;
it is required when building manually. Compose and the image scanner supply it
explicitly. Existing application binaries and features are unchanged by this step.

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
docker buildx build --load --build-context trust-policy=gateway/images/trust-policy \
  --tag ambicrafted/qdrant:1.19.2-security.20261021-r2 \
  gateway/images/qdrant

# Historical comparison target: does NOT apply the final CA trust policy.
# Do not use this target as a qualified deployment image.
docker buildx build --load --build-context trust-policy=gateway/images/trust-policy --target apt-ui \
  --tag ambicrafted/qdrant:1.19.2-security.20261021-apt \
  gateway/images/qdrant
```

Use this directory as the primary build context and the explicitly named public
`trust-policy` context. `.dockerignore` explicitly permits
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

The second security revision removes the vulnerable `braces` dependency through
real, compatible updates to its two parents: `@parcel/watcher` 2.6.0 and
`expect` 30.5.2 with its matching Jest helpers. They use maintained `picomatch`
instead of `micromatch`/`braces`. Nothing is deleted from the generated SBOM.
The third revision applies the actual
`liblzma5` 5.8.1-1+deb13u2 security update, preserving package metadata.
See [the Rust LOW review](LOW-REVIEW.md) for the three transitive Rust findings,
checked source usage, compatible fixes and the cost of owning a server rebuild.
The r4 candidate scan on 2026-10-21, using Trivy 0.74.0 and its database updated
2026-10-20 at 19:12 UTC, reports zero CRITICAL/HIGH/UNKNOWN findings, with 23
MEDIUM and 11 LOW findings still visible. This dated result is not a claim that
all advisories are resolved or that the running service has been upgraded.

The fourth revision updates the real locked `follow-redirects` dependency from
1.16.0 to 1.16.1 and rebuilds the dashboard and complete npm inventory. The
maintainer's [sensitive-header escaping advisory](https://github.com/follow-redirects/follow-redirects/security/advisories/GHSA-8r9p-f939-6h3c)
and [array-form header advisory](https://github.com/follow-redirects/follow-redirects/security/advisories/GHSA-q3jh-wrc6-jgq8)
identify the two fixes (CVE-2026-111755 and CVE-2026-111756). This Node HTTP
adapter is part of the build dependency graph; Qdrant serves static browser
assets and has no Node runtime. That exposure distinction does not remove the
package from the inventory or exempt it from the image gate.

Three loopback-only tests exercise real redirects: metacharacter-named sensitive
headers are stripped across origins, array-form headers are normalized and
stripped, and legitimate same-origin credentials remain intact. The same tests
against the official 1.16.0 package fail on both cross-origin leaks and pass the
same-origin control. These checks run in the build's offline network namespace.
Record the Trivy version, database hash and update timestamp with every result:
the refreshed database detected these two HIGH findings after an earlier scan
of the same filesystem had reported none. An OCI index digest can also change
when build attestations change; compare the platform manifest, image config and
layers before concluding that runtime contents differ.

Three additional build checks exercise native subscription, snapshot/glob
exclusions and positive/negative Jest assertions. All 167 dashboard tests and
the actual Vite production build run without a network. npm installation and
these checks run as the unprivileged `node` user, also avoiding the host root
user's shared inotify quota. A failed native watcher check blocks the build.

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
  --old-image ambicrafted/qdrant:1.19.2-security.20261020 \
  --old-version 1.19.2 \
  --new-image ambicrafted/qdrant:1.19.2-security.20261021-r2 \
  --browser \
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

The runtime healthcheck and dashboard HTML are checked. Optional `--browser`
uses the console's locked Playwright installation and Chromium to render the
home, collection list and collection details, verify the actual point count
and alias, reject JavaScript errors and detect external requests. Omit the flag
when browser dependencies are unavailable; the result then makes no browser
claim. For the older 1.19.1 migration, pass that image with `--old-version 1.19.1`.
This is not a load, production-corpus or distributed-cluster test. Snapshot files, logs and
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
