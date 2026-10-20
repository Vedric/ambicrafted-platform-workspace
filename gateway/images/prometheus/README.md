# Prometheus security rebuild

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
docker buildx build --load -t ambicrafted/prometheus:3.15.0-security.20261020 gateway/images/prometheus
docker run --rm --entrypoint promtool \
  --mount "type=bind,source=$PWD/gateway/observability,target=/work,readonly" \
  --workdir /work ambicrafted/prometheus:3.15.0-security.20261020 test rules alerts.test.yml
```

The 20 October candidate scan found 0 CRITICAL / 0 HIGH, with two UNKNOWN
occurrences retained. A clean scan is a dated result, not a permanent guarantee.
The build currently qualifies Linux x86-64; other architectures require their
own compiler artifacts, builds and tests.
