# Qdrant security derivatives

## Server dependency corrections — 2026-10-22, r4

`1.19.2-security.20261022-r4` retains r3's native CA and dashboard corrections
and rebuilds the actual Qdrant 1.19.2 server from upstream commit
`016542aa5deb6c66380bb137badf73d54f742bde`. The narrow lockfile patch updates
`rand` 0.8.5 → 0.8.6 and 0.9.2 → 0.9.3, and `xxhash-rust` 0.8.15 → 0.8.16,
addressing [RUSTSEC-2026-0097](https://rustsec.org/advisories/RUSTSEC-2026-0097.html)
and [GHSA-6g2r-675j-hx59](https://github.com/DoumanAsh/xxhash-rust/security/advisories/GHSA-6g2r-675j-hx59).
The source archive, builder image, mold archive, cargo-sbom crate and patched
Cargo.lock have explicit hashes. Cargo verifies each downloaded crate against
the lock, then builds offline with `--frozen`. The generated Rust SPDX keeps
782 packages; comparison with the upstream inventory changes only those three
package versions. No finding is hidden by editing an inventory alone.

The qualified build is native Linux x86_64 CPU, using Rust 1.98.1, upstream
default features plus `stacktrace`, and the upstream release profile's fat LTO
and single codegen unit. Cargo/CMake worker counts and mold linker threads are
bounded at four; the build-only cargo-sbom installation uses two workers.
There is no ARM or GPU qualification. The local complete Docker command took
892.843 seconds, with a measured compiler RUN cgroup peak of 8.820 GiB including
file cache. The new Rust stages compiled from source; unchanged dashboard,
healthcheck and trust-helper stages used existing cache. This is neither a fully
uncached measurement nor a hosted-runner duration guarantee. The retained Rust
stage cache, including its shared builder base, is approximately 5.79 GiB;
this is not a peak disk measurement. Reserve at least 12 GiB RAM and 25 GiB free
disk before building; an 8 GiB runner does not meet that prerequisite.

Targeted library validation records 293 passing tests, including two native
release checks of the corrected xxhash custom-secret bounds. One upstream rand
doctest remains explicitly ignored; Miri was not run. Nine Qdrant persisted
hashmap tests pass with the patched lock. Those upstream tests always exercise
io_uring: their initial default-seccomp failures are retained, and their passing
run used an ephemeral profile adding only the three io_uring syscalls to the
official Docker default. No host or runtime policy was changed. Separately,
the resulting r4 image passes the synthetic migration, search, persistence,
snapshot recovery and three Chromium dashboard views under **Docker's default
seccomp**, with dropped capabilities, a read-only root filesystem and
`no-new-privileges`. It reports no browser errors, external requests or cleanup
failures. This does not qualify production io_uring, distributed clusters,
production corpora or the complete upstream test suite.

The actual r4 image scan with Trivy 0.74.0 and the same 22 October 07:10 UTC
database reports **0 CRITICAL, 0 HIGH, 23 MEDIUM, 8 LOW and 0 UNKNOWN**, with
**no finding offering a fixed version** in that database. Together, r3 and r4
remove six fixable occurrences from the previous image without new findings.
These are local build and qualification results; hosted CI and promotion are
separate gates. The [21 October Rust review](LOW-REVIEW.md) remains historical;
[ADR 0052](../../../docs/adr/0052-correctifs-images-compatibles.md) records the
subsequent decision to adopt this measured source build.

## Native CA and dashboard test-tool updates — 2026-10-22, r3

`1.19.2-security.20261022-r3` installs Debian's actual
`ca-certificates=20250419+deb13u1` package and regenerates its trust store.
[DSA-6572-1](https://www.debian.org/security/2026/dsa-6572) removes emSign ECC
Root CA G3 and Comodo AAA Services root. The final image replaces the old bundle,
anchors and links completely, and includes the new package records. Build guards
require the exact bundle SHA-256 and 148 anchors before the existing helper's
`--native-prepared` verification. Exported image files independently confirm that
the original 150-anchor set loses exactly these two DER fingerprints; all other
anchors are preserved. No shell or package manager enters the runtime.

The dashboard's locked Vitest family moves from 4.1.11 to 4.1.12, correcting
[manual mock code injection](https://github.com/vitest-dev/vitest/security/advisories/GHSA-qxg6-89mg-rqv8)
and [Windows redirect traversal](https://github.com/vitest-dev/vitest/security/advisories/GHSA-xp26-3454-mjgp).
These affect development mock-server APIs; the image serves compiled static
assets. The actual dashboard is rebuilt and its full npm SPDX regenerated.
All 167 upstream tests and six dependency checks pass. The synthetic fixture
passes migration from the previous r2 image, search/filter/index checks, writes,
restarts, snapshots and pre-upgrade rollback, plus three Chromium dashboard views
with no page errors or external requests. Its temporary resources are removed.

The local Trivy 0.74.0 scan using the 22 October 07:10 UTC database reports
0 CRITICAL, 0 HIGH, 23 MEDIUM, 11 LOW and 0 UNKNOWN. It removes the two Vitest
findings and DSA-6572-1 with no new findings. The three fixable Rust occurrences
remain visible in this historical r3 image: its official Qdrant binary and Rust
SPDX are byte-identical to r2. The separately qualified r4 build above replaces
them; r3 is preserved as an intermediate comparison artifact.

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

This historical revision additionally distrusts the exact compromised emSign ECC
G3 root in its actual operating-system trust stores. See the shared
[trust policy](../trust-policy/README.md) for the fingerprint, native Java handling,
unchanged package inventory, qualification evidence and limits. This is a local
trust-policy change, not a claim that the vendor CA package was upgraded.
The named build context below contains only public policy code and certificates;
it is required when building manually. Compose and the image scanner supply it
explicitly. Existing application binaries and features are unchanged by this step.

## Build targets and runtime contract

The default target rebuilds Qdrant 1.19.2 from the pinned source and patched
Cargo.lock described above. The historical `apt-ui` comparison target preserves
the executable from the pinned official image. Both rebuild Web UI 0.2.15 from
its pinned source commit, a committed npm lockfile and an explicit, reviewable
patch. Neither build promotes itself.

The **default final target is the nonroot, shell-free Debian 13 runtime**.
`apt-ui` is an explicit comparison target retaining the upstream operating-system
image and entrypoint with signed Debian security backports. Existing storage
ownership and the healthcheck still need a controlled migration when replacing
an older root-based deployment.

```sh
# Qualified minimal runtime (the default).
docker buildx build --load --build-context trust-policy=gateway/images/trust-policy \
  --tag ambicrafted/qdrant:1.19.2-security.20261022-r4 \
  gateway/images/qdrant

# Historical comparison target: no rebuilt server or final CA trust helper.
# Do not use this target as a qualified deployment image.
docker buildx build --load --build-context trust-policy=gateway/images/trust-policy --target apt-ui \
  --tag ambicrafted/qdrant:1.19.2-security.20261021-apt \
  gateway/images/qdrant
```

Use this directory as the primary build context and the explicitly named public
`trust-policy` context. `.dockerignore` explicitly permits
the build recipe, npm manifests/lock, source and Cargo.lock patches, and
healthcheck source/tests.
It excludes private configuration, backups and the rest of the repository.
Upstream archives and image references are pinned by checksum/digest; npm checks
locked package integrity. APT preserves Debian signature verification and exact
security package versions. An unavailable pinned input must fail the build.

The dashboard dependency update includes `js-yaml` 4.3.2, Vitest 4.1.12, React
Router 7.18.4 and the subsequently patched `source-map-js` dependency. Consult
the committed lockfile and build evidence for their exact resolved versions.
The small source patch avoids an invalid link when a
card has no destination and disables automatic cloud metadata/release-banner
requests in this private build. Missing cloud data remains `null`; no health,
version or availability data is fabricated. Documentation links remain usable
when an operator chooses to follow them.

The build runs the complete upstream dashboard suite plus its offline-metadata
regression test, compiles the actual static assets and regenerates the complete
npm SPDX inventory, including development dependencies. The regenerated Rust
SPDX inventory remains next to the rebuilt server binary. The minimal image keeps
Debian package records, original checksums and copyright notices for its copied
native libraries. Its bounded HTTP healthcheck is built and tested with pinned
Go 1.27.3, with build information preserved for scanners.

The second security revision removes the vulnerable `braces` dependency through
real, compatible updates to its two parents: `@parcel/watcher` 2.6.0 and
`expect` 30.5.2 with its matching Jest helpers. They use maintained `picomatch`
instead of `micromatch`/`braces`. Nothing is deleted from the generated SBOM.
The third revision applies the actual
`liblzma5` 5.8.1-1+deb13u2 security update, preserving package metadata.
See [the historical Rust LOW review](LOW-REVIEW.md) for the original source usage
review; the 22 October r4 section above records the completed fixes and rebuild.
The earlier candidate scan on 2026-10-21, using Trivy 0.74.0 and its database updated
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
  --old-image ambicrafted/qdrant:1.19.2-security.20261022-r3 \
  --old-version 1.19.2 \
  --new-image ambicrafted/qdrant:1.19.2-security.20261022-r4 \
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
