# Grafana signed-plugin derivative

The immutable official 13.2.2 base is retained. Six bundled plugin directories are
replaced by complete official signed archives pinned by SHA-256. Their downloaded
versions and provenance are recorded in `plugins-provenance.json`. OpenSSL packages
are pinned to the qualified patched versions. Missing pinned packages fail the build.

Plugin contents and MANIFEST files are never edited after download; signature
validation stays enabled. The disposable qualification verified all 13 signatures,
datasource health and dashboard rendering against synthetic Prometheus/Tempo data.

The seven-image scan still reports **9 HIGH** findings in the Grafana executable
and bundled plugins. This is a reduction, not a clean security sign-off. Preserve
AGPL and plugin notices and the immutable upstream reference. See the
[current security assessment](../../../docs/SECURITY-REFINEMENT-2026-09-27.md).
