# Grafana private security distribution

## Brotli correction — 2026-10-24

The current derivative is `13.2.4-security.20261024.1`, locally qualified as
`sha256:3f4187233880350e6acdeed1726c72d14d036930232fc4d35d1b2869cb552730`.
It installs Alpine's signed, SHA-256-pinned `brotli-libs=1.2.1-r0`. Backend and
plugin source recipes and signature checks remain unchanged. Full synthetic
qualification passes queries, trace correlations, exemplars, service graphs,
SLO coverage semantics and all 48 browser/theme/viewport variants. The scan
reports 0 HIGH/CRITICAL and one UNKNOWN record. The verifier explicitly gives
its public temporary configs mode 0644 for non-root containers under `umask 077`;
its temporary credential file remains 0600. See the
[24 October qualification](../../../docs/QUALIFICATION-2026-10-24.md).
Older tags and build commands below describe their dated recipes; use the new
tag for the current Dockerfile.


## Available native-library fixes — 2026-10-22

The `13.2.4-security.20261022.2` derivative upgrades only Alpine musl and
musl-utils from **1.2.6-r2 to 1.2.6-r3**, the correction for
CVE-2026-107891 recorded by the [Alpine 3.24 security feed](https://secdb.alpinelinux.org/v3.24/main.json).
The exact official APK archives are pinned by URL and SHA-256, their
signatures are verified using the base image keys, and installation runs
without network access. An empty key directory causes verification to fail.
Grafana, the two signed plugin bundles and their source/provenance files
are unchanged: 491 files match the previous image byte for byte.

Exact qualified local image:
`sha256:74e980c0c95cd1c5367882183adf1d80f60e0175e0df5ab7ea7b1491b483399d`.
The 22 October Trivy database reports 0 CRITICAL, HIGH, MEDIUM or LOW and
one UNKNOWN finding, [GO-2026-5932](https://pkg.go.dev/vuln/GO-2026-5932).
That module-level advisory has no fixed version and concerns the deprecated
`golang.org/x/crypto/openpgp` package. The compiled Grafana package closure
excludes that package; the module is retained for other cryptography.
The finding remains visible rather than being suppressed.

The isolated functional qualifier passes authentication, both plugin
signatures, twelve provisioned dashboards, 103 panel queries, 90 rules,
Prometheus and Tempo queries, TraceQL, exemplars, the service graph and
cleanup. The browser rendering test was not repeated for this libc-only
change; backend, plugin and frontend bytes remain identical.

```sh
docker buildx build --load --platform linux/amd64 \
  --build-context trust-policy=gateway/images/trust-policy \
  --tag ambicrafted/grafana:13.2.4-security.20261022.2 \
  gateway/images/grafana
```

## Targeted trust correction — 2026-10-21

The current dated image additionally distrusts the exact compromised emSign ECC
G3 root in its actual operating-system trust stores. See the shared
[trust policy](../trust-policy/README.md) for the fingerprint, native Java handling,
unchanged package inventory, qualification evidence and limits. This is a local
trust-policy change, not a claim that the vendor CA package was upgraded.
The named build context below contains only public policy code and certificates;
it is required when building manually. Compose and the image scanner supply it
explicitly. Existing application binaries and features are unchanged by this step.

This Linux/amd64 candidate rebuilds Grafana **13.2.4** from its pinned source
with Go **1.27.3**, `kin-openapi` **0.149.0** and a bounded private plugin signing
authority. The backend reports `13.2.4+ambicrafted.20261020.r2`. The prior 20 October `r4` image identifies the corrected zlib runtime and compiled-package inventory.
These are derivative versions, not official Grafana Labs releases.

Only **Prometheus and Tempo** external data sources are included. Authenticated
read-only inventory of the existing instance found four datasource records using
those two types, six dashboards with 102 content panels, builtin panel types and
no alert rules. Eleven unused external sources are deliberately removed:
Elasticsearch, PostgreSQL, Pyroscope, InfluxDB, Jaeger, Loki, MSSQL, MySQL,
OpenTSDB, Google Cloud Monitoring and Zipkin. Their removal is a declared
capability reduction; adding one later requires a new reviewed build. Builtin
panels, existing datasource IDs, queries and dashboard assets remain supported.
Automatic preinstallation and automatic plugin updates are disabled in the image.

## Artifact identity and signatures

`plugin-build-inputs.json` pins source commits, archive SHA-256 values, original
frontend archives and derivative versions. Each plugin backend is rebuilt using
its upstream Mage SDK build path, exact Go locks and corrected `x/net` 0.60.0.
Frontend assets remain those of the pinned official archives; plugin metadata
truthfully identifies the modified version. Each bundle includes the full patched
backend source archive, attribution and license notices.

The Tempo plugin imports only protobuf contracts from Tempo. Instead of carrying
a server-module dependency for that purpose, it compiles the exact protocol files
from official Tempo 3.1.0 revision `77fc4563d1135d0ca2656709c7384c278a9c67b0`
under its internal package. Only import prefixes change. Original and derived
hashes for all 23 files, upstream license notices and an SPDX source component
remain in the bundle. `tempo/protobuf-source-inventory.json` records this scope.
No server/storage implementation is copied or imported, and the build checks
that no `github.com/grafana/tempo/` package remains in the dependency closure.
This is an explicit source extraction, not an invented Go module version.

The offline key is **not** a Grafana Labs signing identity. Its public fingerprint
is `9927b7037e53a8156725792ff5fdd4382c05e115`. The core compiles that exact key,
two plugin IDs/versions and SHA-256 of each complete armored `MANIFEST.txt`.
Every signature must verify cryptographically. Upstream checks still validate
all file hashes, missing/additional files, IDs, versions and private root URLs.
Official Grafana signature verification is unchanged and its tests still run.
No `allow_loading_unsigned_plugins`, environment-driven trust root, key-download
fallback or signature-status override is introduced.

The only signed root URLs are `http://localhost:3000/` and
`http://127.0.0.1:3000/`. A different externally configured Grafana root URL
requires a newly reviewed signed release. Internal bridge URLs used by tests do
not change Grafana's configured root URL.

## Rebuild and qualify the existing release

No private key is needed to reproduce this release. The build assembles the
public pinned inputs and fails if any byte differs from the committed signed
inventory. `.dockerignore` admits only the required public files.

```sh
docker buildx build --load --build-context trust-policy=gateway/images/trust-policy \
  --tag ambicrafted/grafana:13.2.4-security.20261021 gateway/images/grafana
uv run --project apps/control-api --no-sync python \
  gateway/images/grafana/qualifier-signatures.py \
  --image ambicrafted/grafana:13.2.4-security.20261021 \
  --output /absolute/path/to/new-signature-evidence
uv run --project apps/control-api --no-sync python \
  gateway/images/grafana/qualifier.py \
  --image ambicrafted/grafana:13.2.4-security.20261021 \
  --output /absolute/path/to/new-grafana-evidence \
  --browser gateway/images/grafana/qualifier-browser.mjs
```

The build runs four packaging/refusal tests, upstream plugin tests under the Go
race detector, copied protocol tests, Grafana signature/loader tests and the
existing alert-validation/OpenAPI tests. The loader integration test checks both
actual bundles, including tampering, missing/extra files and wrong root URL.
The short OpenAPI tests exclude the upstream remote APIs.guru corpus; this is
not the entire Grafana test suite.

The runtime refusal qualifier starts real Grafana eight times: valid baseline,
modified executable, missing file, additional file, changed whole manifest,
foreign key ID, unsigned plugin and wrong root URL. Forbidden plugins must not
be registered; the unmodified datasource must continue loading where applicable.
The functional qualifier verifies authentication, private signatures, absence of
the removed plugins, all six dashboards, Prometheus query data and the actual
synthetic Tempo trace through traceId and TraceQL. Search indexing is polled with
a strict 30-second bound. Playwright renders all 102 panels without JavaScript
exceptions. Empty application time series in the isolated fixture are expected.

These qualifiers require a local Linux Docker Engine and installed console
Playwright/Chromium. They use unique internal networks, ephemeral state and
random synthetic credentials, publish no ports and never mount live volumes.
Only their own resources are removed; cleanup failures fail qualification.
They do not establish cross-version production database migration compatibility.

## Creating a new signed release

1. Review current catalog/source and the actual datasource/alert/panel inventory.
   Prefer a maintained official corrected plugin when available. Update public
   source/archive pins, exact locks, derived versions and deterministic Mage
   build metadata together. Never relabel an old binary or erase its inventory.
2. Build `--target prometheus-build` and `--target tempo-build`. Copy each target's
   `/prepared/<id>` directory from a stopped temporary container into an operator
   staging directory outside the checkout. These targets require no signing key.
3. Review the resulting source inventories, tests and full binary scans before
   invoking `sign_distribution.py PRIVATE_GNUPG_DIRECTORY PREPARED_DIRECTORY
   gateway/images/grafana`. That offline step writes only public signed manifests
   and their policy digests into the checkout. It never runs inside Docker.
4. Rebuild the final core and image, repeat negative loader tests, actual queries,
   dashboards, complete scans and independent review. Promotion remains separate
   and requires a verified backup/rollback plan and an unchanged security gate.

The private RSA3072 signing key is operator state outside both checkout and build
context (directory mode 0700; key files mode 0600), with a two-year expiry. Back
it up in a separate encrypted off-host archive; an untested local key directory
is not a disaster-recovery guarantee. Do not put it in application backups,
container images, logs or Git. A lost key does not prevent rebuilding the existing
release, but a new release requires deliberate key rotation. Rotate before
expiry, or immediately after suspected compromise: generate a new offline key,
review its public fingerprint, re-sign the reviewed artifacts and rebuild the
compiled policy. A stolen key alone cannot approve different bytes under the old
whole-manifest pins; changing the policy/core is still required. Preserve the
previous qualified image and state for controlled rollback.

## Scan interpretation and maintenance

The 2026-10-21 candidate scan with Trivy 0.69.1 reports **zero CRITICAL, HIGH,
MEDIUM and LOW** findings. The real runtime zlib package is upgraded to
1.3.2-r1. One UNKNOWN remains: GO-2026-5932 concerns the unmaintained
`golang.org/x/crypto/openpgp` package. This distribution uses the maintained
ProtonMail implementation. The build explicitly rejects the old package in the
OSS executable's dependency closure and preserves that complete closure as
`/usr/share/grafana/ambicrafted/grafana-packages.txt`. The x/crypto module is still
needed for other packages; its module-level scanner finding remains visible.
This is a usage distinction, not suppression or a claim of universal safety.

The former 56-HIGH image is historical evidence, not this candidate's result.
Source URLs, patches, public signing material, full plugin corresponding source,
AGPL and protocol license notices are preserved. If distributing the derivative,
make its complete corresponding source and build changes available as required
by the upstream licenses. Maintaining this small fork has a real cost: each
plugin update changes the signed manifest and requires a core rebuild/review.
See [ADR 0042](../../../docs/adr/0042-distribution-grafana-privee-corrigee.md).
