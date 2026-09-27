# Tempo security derivative

The image keeps the immutable upstream 3.0.3 runtime and rebuilds its executable
from the pinned source archive. `go.mod` and `go.sum` record the full resolved
dependency graph. The pinned Go toolchain, Thrift, gRPC and OpenTelemetry updates
are compiled together, rather than changing an embedded inventory.

OpenTelemetry core 1.45 requires its matching 0.21 log modules and otelzap 0.20.
See the [official compatibility map](https://github.com/open-telemetry/opentelemetry-go-contrib/blob/v1.45.0/versions.yaml).
The build runs upstream startup/configuration and OTLP receiver tests with the race
detector. Its build namespace has eth0 for ring tests and an isolated localhost;
it does not use the running stack or customer state. The final compile has no network.

The runtime retains upstream package metadata and AGPL-3.0 licensing. The source
archive URL, SHA-256 and revision are in the Dockerfile; retain them and the modified
dependency manifests with redistributed builds. No scanning inventory is deleted.

A disposable qualification accepted an OTLP HTTP span, queried it, restarted with
persistent storage and queried it again. The final inventory reports no CRITICAL,
HIGH or MEDIUM findings, with lower/unknown findings retained in the full report.
See [the current security report](../../../docs/SECURITY-REFINEMENT-2026-09-27.md).

Compose runs as UID/GID 10001. For an existing root-owned Tempo volume, stop only
this platform's service, archive its volume privately, and migrate that dedicated
volume to 10001:10001 before starting this image. Never apply ownership changes to
a client volume by guessing its name. Fresh hosts rebuild locally; dated tags are
not published registry digests.
