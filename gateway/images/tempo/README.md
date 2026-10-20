# Tempo security derivative

## Targeted trust correction — 2026-10-21

The current dated image additionally distrusts the exact compromised emSign ECC
G3 root in its actual operating-system trust stores. See the shared
[trust policy](../trust-policy/README.md) for the fingerprint, native Java handling,
unchanged package inventory, qualification evidence and limits. This is a local
trust-policy change, not a claim that the vendor CA package was upgraded.
The named build context below contains only public policy code and certificates;
it is required when building manually. Compose and the image scanner supply it
explicitly. Existing application binaries and features are unchanged by this step.

The image starts from the immutable upstream 3.0.3 runtime and rebuilds its executable
from the pinned source archive. `go.mod` and `go.sum` record the full resolved
dependency graph. The pinned Go toolchain, Thrift, gRPC and OpenTelemetry updates
are compiled together, rather than changing an embedded inventory.

OpenTelemetry core 1.45 requires its matching 0.21 log modules and otelzap 0.20.
See the [official compatibility map](https://github.com/open-telemetry/opentelemetry-go-contrib/blob/v1.45.0/versions.yaml).
The build runs upstream startup/configuration and OTLP receiver tests with the race
detector. Its build namespace has eth0 for ring tests and an isolated localhost;
it does not use the running stack or customer state. The final compile has no network.

The second revision also aligns all five OTLP trace/metric exporter modules to
1.45.0. In particular, the three trace modules previously retained 1.43.0 and
were affected by [CVE-2026-81870](https://github.com/open-telemetry/opentelemetry-go/security/advisories/GHSA-8wmf-6v46-5gfg).
The image build now tests client/exporter diagnostic privacy directly and delivers
an actual span to an isolated OTLP HTTP fixture. A separate negative control with
the old 1.43.0 exporters fails all four privacy cases even with SDK 1.45.0; merely
upgrading the SDK cannot make this regression test pass.

The third revision also replaces the actual timezone package with official Debian
`tzdata` 2026c-0+deb12u1 (DLA-4792-1). Its archive SHA-256 comes from authenticated
bookworm-security metadata and is pinned in the build. All package files, control
metadata and checksums move together; the build checks every package checksum and
that all former regular-file paths are replaced. The final image contains no added
package manager. A full exported-filesystem comparison proves that only tzdata
content/metadata changed from revision two and that the server bytes are identical.

The runtime retains package metadata and AGPL-3.0 licensing. The source
archive URL, SHA-256 and revision are in the Dockerfile; retain them and the modified
dependency manifests with redistributed builds. No scanning inventory is deleted.

A disposable qualification accepted an OTLP HTTP span on the previous image,
upgraded the same synthetic volume, queried that trace, ingested a new trace,
rejected malformed OTLP with HTTP 400, restarted and queried both traces again.
The `3.0.3-security.20261020-r3` candidate scan has zero CRITICAL, HIGH, MEDIUM
or LOW findings and one UNKNOWN finding retained. This does not assert that
the live service was upgraded. The remaining UNKNOWN is GO-2026-5932 for the
unmaintained `golang.org/x/crypto/openpgp` package at module-inventory level; no
fixed module version is published. It stays visible, without suppression.
See [the current candidate qualification](../../../docs/QUALIFICATION-2026-10-20.md);
the [27 September report](../../../docs/SECURITY-REFINEMENT-2026-09-27.md)
remains historical.

```sh
docker buildx build --load --build-context trust-policy=gateway/images/trust-policy --tag ambicrafted/tempo:3.0.3-security.20261021 gateway/images/tempo
uv run --project apps/control-api --no-sync python gateway/images/tempo/qualifier.py \
  --old-image ambicrafted/tempo:3.0.3-security.20261020 \
  --new-image ambicrafted/tempo:3.0.3-security.20261021 \
  --output /absolute/path/to/new-tempo-evidence
```

The qualifier requires Linux Docker, creates a private internal network and a
unique volume, publishes no host port, and removes only its own resources.
Logs and traces are synthetic. Cleanup failure fails qualification. This is
not a load, distributed-cluster or production-corpus test.

Compose runs as UID/GID 10001. For an existing root-owned Tempo volume, stop only
this platform's service, archive its volume privately, and migrate that dedicated
volume to 10001:10001 before starting this image. Never apply ownership changes to
a client volume by guessing its name. Fresh hosts rebuild locally; dated tags are
not published registry digests.
