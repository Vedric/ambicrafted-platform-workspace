# ADR 0016 — Coordinated dependency updates and explicit PostgreSQL migration

Date: 2026-09-27

Status: Accepted; PostgreSQL major migration deferred

## Context

Dependabot opened eleven application/tooling updates and a PostgreSQL 16 to 18
update. Several application PRs updated the agent manifest and its lock without
updating the control API lock, which also records the editable agent metadata.
The API therefore rejected installation with `--locked`, even when its resolved
runtime dependency was already recent enough.

jsdom 30.1.1 brings a transitive dependency whose Node requirement excludes the
previously pinned 22.22.0 runtime. Ruff 0.16 adds diagnostics to projects still
using 0.15. Build backends and CI actions also have reviewed pinned updates.

The PostgreSQL PR only replaces Dockerfile bases. Existing Compose configuration
uses a PostgreSQL 16 volume layout and a qualified, locally corrected image.
PostgreSQL 18 changes the default data directory and volume mount, and changing
an image never performs the required major-version data migration.

## Decision

Apply the compatible application/tooling changes as one reviewed maintenance
batch. Keep MCP 2.2.0 and Pydantic 2.13.5 coherent across the standalone agent,
runbooks server and control API; use LangGraph 1.2.12 in the agent and API. Keep
bounded compatible manifests and commit all affected resolved locks, including
the API's editable-agent metadata. Use Ruff 0.16.9 throughout and uv_build
0.12.18 for the three distributed Python packages. The uv executable remains
explicitly pinned to 0.12.5.

Use Node 22.23.3 from the maintained Node 22 line, recorded in `.node-version`
and read by both JavaScript CI jobs. Keep npm 11.10.0. Both npm projects reject
older Node versions through their engine constraints. Retain `engine-strict`
and adopt jsdom 30.1.1. CI actions remain pinned by their verified upstream
commit identifiers, not mutable release tags.

Correct Ruff findings without broad rule exclusions. Broad catches that form
the MCP/indexer privacy boundary retain narrow, explained `BLE001` exceptions:
unexpected SDK failures must still be converted to a sanitized operator error.
The checkpoint test only accepts known validation errors instead of swallowing
every exception. Invalid gateway field types raise `TypeError`, caught by the
existing sanitized response boundary.

Keep the PostgreSQL 16.15 corrective image, digest, Compose mount and running
volumes unchanged. Ignore only PostgreSQL semver-major Docker updates in
Dependabot; continue minor/patch and digest monitoring. Close PR #2 as a deferred
major migration when final PR processing occurs, not as an already applied
update. This decision does not accept or waive the dated container findings.

A future PostgreSQL major update requires its own migration change: review
intervening release notes, qualify dump/restore or `pg_upgrade` against a copy,
adapt the versioned volume layout, verify LiteLLM schema/application behavior,
restart and backup/restore, and retain a tested rollback. Do not qualify against
the live PostgreSQL volume. See the [PostgreSQL migration guide](https://www.postgresql.org/docs/18/upgrading.html)
and the [official image's PGDATA documentation](https://github.com/docker-library/docs/blob/master/postgres/README.md#pgdata).

## Alternatives rejected

- Merge each generated PR unchanged: this retains stale downstream lock metadata
  and the incompatible Node runtime.
- Drop `--locked`, engine checks or lint rules: this hides the reason installs
  are not reproducible.
- Switch the live PostgreSQL image to 18 with the existing mount: this is not a
  migration and does not preserve the qualified recovery procedure.
- Close all PRs as duplicates immediately: the standalone agent and runbooks
  versions had not been updated, even though the API resolved newer versions.

## Consequences

The batch needs fresh installations for every Python project and both npm
projects, real MCP transport tests, and the browser suite on the retained
application baseline. Updating a shared manifest now requires checking every
downstream lock. Node 22.22.0 installations must be updated before development
or rebuilding the console; prebuilt local UI serving does not execute Node.

This maintenance changes no deployment image or data volume. PostgreSQL 18
benefits remain deferred, and the remaining image vulnerabilities documented in
the security assessment remain open. Local test results are not a hosted CI
result or unconditional production certification. Dependency validation and
upstream provenance are recorded in [the maintenance review](../DEPENDENCY-UPDATES-2026-09-27.md).
