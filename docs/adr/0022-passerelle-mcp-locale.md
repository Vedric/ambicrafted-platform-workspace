# ADR 0022 — One bounded local MCP gateway and measured usage budgets

Date: 2026-09-27. Status: accepted for the private local platform; release
qualification and residual security findings are recorded separately.

## Context

The checkout exposed separate runbooks and control MCP servers. ATLAS launched
the runbooks server directly, while readiness probed each backend independently.
This duplicated client routing and made a common authority boundary difficult to
inspect. The user requested a common MCP gateway and efficient tool/token usage.
The private single-operator scope does not require an HTTP MCP service, remote
identity federation, dynamic registration or another database.

Token telemetry also conflated missing counters with zero. Local API cost headers
can be absent without implying that hardware or electricity is free. A limit on
reported tokens cannot predict the provider's next input token count.

## Decision

Introduce NEXUS as one local stdio service in the existing control-API package,
using the pinned MCP SDK. Two fixed trusted subprocess backends expose closed
namespaced allowlists. Complete operator connections see four runbook and eleven
control tools. The ATLAS profile launches only the runbooks backend and passes
only its four tool schemas to the model. Existing API identifiers and source
provenance checks are retained. Human decisions and operations stay outside MCP.

Validate advertised read-only metadata, preserve standard schemas, reject
collisions and oversized inventories, bound calls and results, refuse concurrent
calls to the same backend and isolate backend failures. Forward filtered
environments and keep exception details off protocol output. Close children on
normal exit, cancellation and SIGTERM. The gateway does not sandbox code running
as the same OS user, or enforce raw-frame limits before SDK parsing.

Add a configurable cumulative **observed** SRE token ceiling, bounded completion
size, attempted-call accounting and nullable token/cost telemetry with coverage.
Preserve checkpointed accounting. Refuse the next dispatch at the ceiling and
record a final-response overshoot. Do not estimate unknown usage, tokenization,
hardware cost or missing historical coverage.

This replaces client-routing details in ADRs 0002, 0003 and 0014, and refines
reported-budget semantics without weakening the confidentiality or approval
boundaries of ADRs 0009 and 0010. Earlier records remain unchanged.

## Alternatives rejected

- An HTTP gateway and OAuth add ports, credentials and operational lifecycle
  without meeting an additional requirement in this local stdio deployment.
- A third-party gateway platform, registry or service mesh adds a separate
  dependency and dynamic authority surface for only two fixed backends.
- In-process tool imports avoid subprocesses but bypass MCP interoperability and
  couple backend imports, credentials and failures into one runtime.
- Presenting every tool in every prompt wastes context and grants unnecessary
  capabilities. Estimating token usage from character counts creates false
  precision and cannot establish a hard quota.

## Consequences

There is one extra small gateway process per client and a control-API runtime
installation prerequisite for standalone ATLAS. Backends still have separate
lifetimes; a failed backend needs reconnection rather than hidden retries. Client
resource/prompt/task capabilities are intentionally narrower than direct backend
development access. Independent clients do not share a global concurrency quota.

Real stdio tests exercise both production backends through an authenticated
synthetic loopback API, metadata, collisions, refusals, timeout, cancellation and
shutdown. SRE tests cover partial/missing/invalid telemetry, attempted calls,
checkpoint replay and observed overshoot. None establishes model correctness,
third-party client compatibility in every editor, or security certification of
the complete production stack. See [the gateway guide](../MCP-GATEWAY.md) for
commands, exact limits, environment handling and report fields.
