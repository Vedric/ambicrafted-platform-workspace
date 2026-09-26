# ADR 0010: private console and shared control plane

Date: 2026-09-26. Status: accepted.

## Context

The owner wants a complete, responsive agentic platform usable through a CLI
or a modern UI, and explicitly chose private local access. Existing incident
contracts, confidential routing and human approval must hold through both.

## Decision

- A React/TypeScript console is served by a FastAPI control plane on loopback.
  Static assets and fonts are self-hosted. No external browser telemetry runs.
- The CLI and UI share authenticated API operations. CLI credentials stay in
  the private root environment. Browser sessions use opaque HttpOnly cookies,
  explicit CSRF protection, origin checks and short-lived one-use login tickets.
  A local CLI can open an authenticated browser without displaying credentials.
- Analyses run in isolated subprocesses through the existing CLI contracts.
  A bounded queue serializes inference. Raw alerts remain in memory and reach
  the child on stdin; reports and operation metadata are private local state.
  A restart marks unfinished work interrupted instead of silently replaying it.
- A streamed event channel reports actual execution stages. The console never
  invents percentages, live metrics, successful approvals or model confidence.
- Human runbook editing uses confined paths, version checks and atomic writes.
  It does not give agents a write tool. Index publication remains a separate
  explicit operation using the existing atomic alias mechanism.
- Operational actions are fixed, typed commands, never arbitrary shell input.
  They cover health, indexing, backup and isolated restore validation. Audit
  events record identifiers and operation types, never raw incidents or keys.
- The production target here is a single trusted workstation operator. Remote
  multi-user exposure requires a separate deployment/authentication design.

## Consequences

There is one source of incident truth and one authorization boundary for both
entry points. Sessions, queue recovery, cancellation, provenance and file changes
need integration tests, while browser tests cover keyboard, responsive layouts,
accessibility, errors and real user flows. Reduced-motion preferences are honored.

Local binding does not authenticate another local process by itself. Mandatory
credentials, Host/Origin checks and CSRF validation are complementary controls.
A UI cannot establish the semantic correctness of a diagnosis or remove known
upstream vulnerabilities; these remain visible, dated operational findings.

References: [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/),
[OWASP CSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html),
[OWASP session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
