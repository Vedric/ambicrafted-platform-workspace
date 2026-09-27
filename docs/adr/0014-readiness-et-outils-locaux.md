# ADR 0014 — Measured local readiness and read-only operator MCP

Status: accepted. Date: 2026-09-27.

## Context

Service health alone does not tell an operator whether an installed checkout can
run an analysis, use its local knowledge or speak in a selected language. A
capability catalogue describes intended behavior but does not prove that a local
dependency is installed or responding. Conversely, passing these checks cannot
settle documented image vulnerabilities or approve remote multi-user deployment.

The platform remains a single trusted operator's private local workspace. Client
content must remain local, and MCP must not bypass human decisions.

## Decision

Expose authenticated `GET /api/preparation` with a versioned checklist, measured
evidence, timestamps, feature prerequisites and explicit qualification limits.
The CLI aliases `preparation` and `doctor` consume that exact endpoint. Required
check failures make `ready` false and the diagnostic CLI exit with status 2.

Probe only fixed local destinations and fixed installed executables. Readiness
reads package metadata, permissions, source counts, gateway alias inventory,
service health, optional voice status and real MCP stdio handshakes. It never
sends a client prompt, downloads a model, installs a dependency, executes a shell
or repairs the machine. Suggested commands remain inert operator guidance.
Independent deadlines isolate failures; a short cache coalesces concurrent UI,
CLI and MCP requests. No exception details, credentials or source text enter the
diagnostic response.

Extend the existing control MCP to nine read-only tools: health, preparation,
catalogue, analysis list/detail, runbook list/read, search and bounded audit.
These adapt existing authenticated GET routes, with a dedicated bounded audit
endpoint, explicit validation, no redirects and bounded response bodies. There
is no mutation or approval tool. Validate this property through real stdio/HTTP
protocol tests, invalid-input tests and before/after audit/state comparisons.

Voice and dialogue accept the validated language set `en|fr`, defaulting to `en`.
The HTTP API and CLI forward that selection to the offline voice runtime. Readiness
reports each installed language independently rather than asserting that a
browser microphone or speaker has been tested.

## Consequences

The operator receives useful local evidence without treating an installation
check as production certification. Missing optional voice or observability does
not prevent text analysis, while missing core prerequisites remain explicit.

The diagnostic depends on a running control API; a failed API still requires local
service-manager diagnosis. HTTP health does not prove inference quality, alias
inventory does not certify provider routing, vector presence does not prove index
freshness, and MCP tool declarations do not enforce a consumer's data handling.
Use the tools only with trusted local confidential consumers. Vulnerability
triage, restore qualification, capacity testing and remote identity/isolation
remain separate release requirements.
