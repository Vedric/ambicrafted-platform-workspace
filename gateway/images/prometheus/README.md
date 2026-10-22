# Prometheus security rebuild

## Additional native trust correction — 22 October 2026

The current dated image also removes the exact Comodo AAA root required by
[DSA-6572-1](https://www.debian.org/security/2026/dsa-6572), after the earlier G3
correction. All other anchors and application executable bytes are unchanged.
The effective bundle now contains 148 roots; native Go verification accepts AAA
in the previous image and refuses it in the corrected image, while the unrelated
control remains accepted. See the [shared policy](../trust-policy/README.md) for
both fingerprints, provenance and the distinction from a native package update.
No finding or package inventory is suppressed.

## Targeted trust correction — 2026-10-21

The current dated image additionally distrusts the exact compromised emSign ECC
G3 root in its actual operating-system trust stores. See the shared
[trust policy](../trust-policy/README.md) for the fingerprint, native Java handling,
unchanged package inventory, qualification evidence and limits. This is a local
trust-policy change, not a claim that the vendor CA package was upgraded.
The named build context below contains only public policy code and certificates;
it is required when building manually. Compose and the image scanner supply it
explicitly. Existing application binaries and features are unchanged by this step.

Prometheus 3.15.0 is rebuilt from its exact upstream commit using Go 1.27.3 and
`golang.org/x/net` 0.60.0 with its compatible Go module family. The source archive,
compiler archive, official web UI archive and upstream runtime image are pinned
by SHA-256. Committed Go locks are verified before compilation.

Both `prometheus` and `promtool` are replaced. The official embedded web UI,
runtime permissions, entrypoint, licenses, configuration and OS package metadata
remain available. No advisory is suppressed and no package inventory is removed.
Upstream configuration, rule and HTTP API tests run with the race detector before
building. The repository's alert-rule tests remain a separate functional check.

```sh
docker buildx build --load --build-context trust-policy=gateway/images/trust-policy -t ambicrafted/prometheus:3.15.0-security.20261022 gateway/images/prometheus
docker run --rm --entrypoint promtool \
  --mount "type=bind,source=$PWD/gateway/observability,target=/work,readonly" \
  --workdir /work ambicrafted/prometheus:3.15.0-security.20261022 test rules alerts.test.yml
```

The 20 October candidate scan found 0 CRITICAL / 0 HIGH, with two UNKNOWN
occurrences retained. A clean scan is a dated result, not a permanent guarantee.
The build currently qualifies Linux x86-64; other architectures require their
own compiler artifacts, builds and tests.
