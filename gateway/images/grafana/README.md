# Grafana source and signed-plugin derivative

This Linux/amd64 derivative uses the immutable official Grafana **13.2.4** base.
The backend is genuinely rebuilt from its exact upstream source commit with
Go **1.27.3** and `kin-openapi` **0.149.0**. The only resulting module changes are
`kin-openapi` and its `jsonschema` dependency, as recorded in
`core-dependencies.patch`. The build verifies the source archive, compiler image,
and resulting `go.mod`/`go.sum` checksums. `core-provenance.json` records their
identities; the executable reports `13.2.4+ambicrafted.20261020`.

OpenTSDB 13.0.5 and Google Cloud Monitoring (`stackdriver`) 12.6.3 are installed
from complete official signed archives, each pinned by SHA-256. Eleven other
bundled plugin directories remain exactly as supplied by the base image.
`plugins-provenance.json` records all thirteen versions and the two downloads.
No binary metadata, plugin content or signature manifest is altered. Plugin
signature verification remains enabled.

## Build and qualification

From the repository root:

```sh
docker buildx build --load \
  --tag platform/grafana:13.2.4-security20261020 gateway/images/grafana
uv run --project apps/control-api --no-sync python \
  gateway/images/grafana/qualifier.py \
  --image platform/grafana:13.2.4-security20261020 \
  --output /absolute/path/to/new-grafana-evidence \
  --browser gateway/images/grafana/qualifier-browser.mjs
```

The build runs the upstream alert-rule validation, OpenAPI parser and OpenAPI
request-filter tests with `go test -short`. The short mode deliberately excludes
the upstream remote APIs.guru corpus download. It is not the full Grafana test
suite or a cross-version production database migration test.

The qualifier requires a **local Linux Docker Engine**, the console's installed
Playwright package/Chromium, and the two pinned synthetic fixture images declared
in `qualifier.py`. It creates an internal network, disposable state and random
temporary credentials. The host accesses the private bridge directly; no ports
are published and containers have no external network access. A conflicting
private subnet fails explicitly. Docker Desktop remote engines require a
separately adapted test runner; they are not silently given an external network.

Checks cover startup, the reported backend version, authentication, all thirteen
plugin signatures/versions, both provisioned datasources, six EN/FR dashboards,
a real Prometheus query and a synthetic Tempo trace through Grafana's datasource
API. The browser loads all six dashboards, captures screenshots and checks for
JavaScript exceptions. Empty application series are expected because the fixture
does not invent AURA, token or SRE measurements. Screenshots prove rendering,
not production metric coverage or long-term retention.

Logs and `qualification.json` stay in the selected evidence directory. The
generated credential enters the browser through stdin and is redacted from
diagnostics. Only resources created by the qualifier are removed; cleanup
failures make qualification fail.

## Security boundary and remaining findings

The 2026-10-20 Trivy 0.74.0 scan of this built image reports **0 CRITICAL,
56 HIGH, 173 MEDIUM, 13 LOW and 5 UNKNOWN** package/CVE occurrences. The five
`kin-openapi` HIGH findings in the unmodified 13.2.4 backend are gone. All remaining
HIGH findings are in official signed datasource executables, including the
required Prometheus and Tempo plugins. Current official catalog archives still
contain the affected Go/dependency versions.

This is **not** a clean security sign-off. The repository's CRITICAL/HIGH release
gate must stay red until suitable signed upstream fixes or a separately reviewed
implementation are qualified. There is no vulnerability suppression, unsigned
plugin exception or metadata-only change. Removing the optional plugins alone
would leave the required plugins affected; removing files without controlling
preinstallation can also cause automatic downloads.

Keep the service private and authenticated. Those deployment controls reduce
exposure; they do not erase the findings. Preserve the AGPL license, upstream and
plugin notices, corresponding source and this derivative's patch when
redistributing. See [ADR 0036](../../../docs/adr/0036-grafana-source-et-plugins-signes.md)
for the decision and its maintenance cost.
