# ADR 0037 — Corrective maintenance and release publication gate

Date: 2026-10-20. Status: accepted.

## Context

The recent audit failed on Python dependencies and vulnerable images. Several
image builds had not produced actionable failure diagnostics. A newer upstream
version can retain known vulnerabilities; functional CI cannot replace a complete
scan of the delivered executables.

## Decision

Keep application upgrades targeted, with committed dependency locks. Rebuild the
affected Go executables using Go 1.27.3 and the corrected x/net module family
from pinned upstream sources. Preserve interfaces, assets, licenses and package
metadata. Test the relevant upstream contracts before building.

For LiteLLM, use the 1.104.4 stable line and install the two corrected aiohttp/yarl
wheels offline after SHA-256 verification. Qualify migration, authentication,
restricted aliases, local streaming/embeddings, restart and logical rollback
into a separate database. Running the old gateway against a database migrated
by the new version is not a validated rollback procedure.

The scanner retains a bounded, redacted failure tail, scanned image identity and
a separate result for every service. It does not inherit application credentials.
All eight images have independent jobs, so one failed build does not cancel
the other evidence.

Tagged releases reuse the application CI and image-security workflows. Only
success of both creates a release draft. Publication still requires review of
the evidence and remaining acceptance boundaries; green unit tests alone do not
automatically publish a stable release.

## Rejected alternatives

- Ignoring HIGH findings, removing an SBOM or disabling plugin signatures to
  obtain a green result would remove evidence without correcting the risk.
- Moving every component to its latest major version would add migration cost
  and regression risk without a demonstrated need for this private product.
- Declaring every MCP or feature qualified merely because a package exists
  would confuse installation with a functioning operator workflow.

## Consequences

Derivatives add maintenance cost and longer builds. Sources and dependencies
remain auditable, with Dependabot coverage extended to all eight Docker contexts.
Official Grafana plugin signatures are preserved; remaining vulnerabilities keep
the release gate failed. Hardware support is explicit: Linux/WSL x86-64 for
these builds, with x86-64-v3 required by Neo4j UBI10. Other hosts need qualification.

Audits, model results and long-running tests apply to a specific revision and
scope. An AI engineering review supports development; it is not independent human
acceptance. Off-host backup/key custody, alert receipt and real audio devices
remain separate checks in the operator's environment.
