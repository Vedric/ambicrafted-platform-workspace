# ADR 0005: propagation of the trace context to the gateway

Status: accepted
Date: 2026-08-25
Completes ADR 0004, which observed two disjoint span trees per LLM call and
deferred the decision, because it touches `llm.py`.

## Context

Every LLM call produced two unrelated traces in Tempo: the `llm.*` span of
`sre-agent`, and a `litellm-gateway` trace of 8 to 9 spans, with no common
`trace_id`. Cause: `llm.py` did not send a `traceparent` header. Joining them
means modifying a guardrail. Before doing so, it had to be established that
the gateway would actually make use of that header.

## Preliminary measurement: does the gateway extract a `traceparent`?

Measured, not read. A `curl` to `/v1/chat/completions` (alias `local`) with a
forged header in W3C format:

```
traceparent: 00-54cb2370448e764738e06d8816eb52ff-33cb89ad348d45ce-01
```

then `GET http://tempo:3200/api/traces/54cb2370448e764738e06d8816eb52ff`:
HTTP 200, 9 spans, all from `litellm-gateway`. The root span
`Received Proxy Server Request` (SERVER) carries as `parentSpanId`
**`33cb89ad348d45ce`, the forged span_id**. The gateway (LiteLLM 1.98.0,
`callbacks: ["otel"]`, configuration unchanged) does not merely reuse the
trace identifier: it attaches its server span under the client span it is
given. No orphan trace is created alongside.

Outcome (a): propagation is useful. The fallback correlation by shared
attribute (`x-litellm-call-id` exists in the response headers) was not needed.

## Decision

`llm.py` injects the current context into the request headers through
`opentelemetry.propagate.inject`, inside the `llm.*` span.

What does not change, and is verified by test:

- **The order of the barriers.** Barrier 1 (`FuiteConfidentielle`), then
  budget, then opening of the span, then headers (barrier 2 and
  `traceparent`), then network. A refused payload never gets a header built:
  a test replaces `inject` and `httpx.post` with assertions and verifies that
  neither is reached.
- **The signature of `appeler_llm`.**
- **The behaviour with no active span.** With tracing off (`SRE_TRACAGE=0`),
  the W3C propagator writes nothing: the headers are exactly `Authorization`
  and `Content-Type`, no exception. This is the only case where the change
  could have raised in a path that did not raise; it is locked by a test, not
  by a reading of the SDK.
- **The dependencies.** `opentelemetry.propagate` comes from
  `opentelemetry-api`, already pulled by `opentelemetry-sdk` bounded to
  `>=1.30,<2`. No library added.

Detail noted in testing: SDK 1.44 emits the flags `03` (sampled + random, W3C
Trace Context level 2) rather than `01`. The gateway attaches in both cases.

Tests: 37 original unchanged, 6 added in `tests/test_propagation_trace.py`,
43 in total.

## What this changes in reading traces

Verification, alert `PostgreSQL: too many clients already`, one run per
implementation. The TraceQL query

```
{ resource.service.name = "sre-agent" } && { resource.service.name = "litellm-gateway" }
```

returns exactly one trace per run, rooted at `task.incident_analysis`.

| Trace | spans | `sre-agent` | `litellm-gateway` | LLM calls attached |
|---|--:|--:|--:|--:|
| hand-written loop `5556f616…` | **52** | 10 | 42 | 5 / 5 |
| graph `a6cb95ce…` (up to the gate) | **60** | 18 | 42 | 5 / 5 |
| ADR 0004, graph, before propagation | 19 | 19 | 0 | 0 / 5 |

Each `Received Proxy Server Request` has an `llm.*` span as its parent
(`llm.extraction`, `llm.classification`, `llm.raisonnement` ×3). Sum of input
tokens: 11,193 on both sides, over the same five calls.

**Gap with the prediction.** The curl of the preliminary measurement gave 9
spans per call, hence a prediction of 19 + 5 × 9 = 64. Measured: 60. Two
causes, neither of which is a propagation defect:

- 42 and not 45 on the gateway side: the `postgres` span appears on only 2
  calls out of 5, when the virtual key's authentication is not cached (two
  keys, two cache misses). A call costs 8 or 9 spans.
- 18 and not 19 on the agent side: three tools called instead of four,
  generation variance, not trace variance.

**What is not propagated**, and what must be known when reading Tempo:

1. **The embedding of the `semantic_search` query.** The MCP server calls
   `/v1/embeddings` (alias `local-embed`) with its own `httpx`, in its own
   process, without OTel. Measured on the hand-written loop: an orphan
   `litellm-gateway` trace of 5 spans and 2.3 s, `url.path = /v1/embeddings`,
   `litellm.model_group = local-embed`, entirely contained within the window
   of `tool.semantic_search` (2.4 s). That path does not go through `llm.py`:
   outside the scope of this ADR, and the reason why a `tool.semantic_search`
   will remain a leaf in the unified trace.
2. **The `MCP send …` spans of the `mcp` SDK 2.1.0.** Found during
   verification: the SDK emits its own spans (scope `mcp-python-sdk`, service
   `sre-agent`): `initialize`, `tools/list`, one `tools/call` per tool. They
   are **roots**, one trace each, because the MCP client runs in a thread with
   its own event loop (`outils.py`) where the context of the `tool.*` span is
   not carried. The SDK does inject a `traceparent` into `_meta` (SEP-414),
   but it is the identifier of that orphan trace that it transmits to the
   server. Predates this ADR, invisible as long as nobody looked for an
   overlap. Joining that path requires two things outside the scope: passing
   the context to the MCP thread, and instrumenting the server. To be decided
   separately.

**Reading.** An alert trace is now made up 70–80% of gateway spans (42 out of
52 or 60), including ten `router` and five `batch_write_to_db`. In Grafana,
collapsing the `Received Proxy Server Request` nodes gives back the view of
ADR 0003; expanding them gives, per call, the time spent in authentication,
in routing and at the provider. The orchestration calculation of ADR 0004
(parent span minus `llm.*` and `tool.*`) remains valid: the gateway spans are
descendants of `llm.*`, already counted.

## The open point of ADR 0004: the five shared `gen_ai.*` keys

Unification makes it possible to measure the conflict on **the same call**,
which was impossible before. Result, over the five calls of the two runs:

| Key | `sre-agent` (`llm.*`) | `litellm-gateway` (`litellm_request`) | agreement |
|---|---|---|---|
| `gen_ai.system` | `anthropic`, `ollama_chat` | same | yes |
| `gen_ai.response.model` | the alias | the alias | yes |
| `gen_ai.usage.input_tokens` | 746, 467, 2598, 3123, 4259 | same | yes |
| `gen_ai.usage.output_tokens` | 2373, 82, 124, 150, 1068 | same | yes |
| `gen_ai.request.model` | **the alias** (`smart`, `fast`, `local`) | **the provider model** | **no** |

The conflict of meaning reduces to one key, `gen_ai.request.model`. The other
four carry the same value on both sides, which creates a different problem:
duplication.

**Made worse for aggregates.** A sum per trace with no service filter counts
each call twice. Measured:

```
{ trace:id = "5556f6169e19ab41f1af9712445fdec9" && span.gen_ai.usage.input_tokens > 0 }
  | sum(span.gen_ai.usage.input_tokens) > 0
→ 22,386 (10 spans)

{ trace:id = "5556f6169e19ab41f1af9712445fdec9" && resource.service.name = "sre-agent"
  && span.gen_ai.usage.input_tokens > 0 } | sum(span.gen_ai.usage.input_tokens) > 0
→ 11,193 (5 spans)
```

Before unification, the same sum over a trace was correct because the trace
had only one service. It is now wrong by a factor of exactly 2 as soon as
`resource.service.name` is forgotten. Rule for any dashboard: **no
`gen_ai.usage.*` or `ambicrafted.cost_usd` aggregate without a service
filter.**

**Clarified for resolution.** The alias → model relation, which was readable
nowhere, becomes a queryable parent-child relation:

```
{ resource.service.name = "sre-agent" && span.gen_ai.request.model = "smart" }
  >> { resource.service.name = "litellm-gateway" && name = "litellm_request" }
  | select(span.gen_ai.request.model, span.gen_ai.response.model)
```

returns, on the unified trace, the three `litellm_request` descendants of the
`llm.raisonnement` spans, with the provider name the gateway resolved behind
`smart`. The same query with `"local"` returns `coder`. This is rule 1 of
CLAUDE.md made verifiable from Tempo: the code knows only the alias, the
gateway alone knows the model, and the trace shows the border between the
two.

Verdict: **both, and it is clear-cut.** The divergent meaning of
`gen_ai.request.model` becomes information (the alias on one side of the
border, its resolution on the other) as soon as one reads by
`resource.service.name`; the duplication of the other four keys becomes an
aggregation trap that did not exist before. Neither is fixed without touching
the gateway's telemetry; that is not done here.

## Consequences

- `llm.py`: +14/−5 lines, one import, one named header dict, one `inject`
  call. Barriers, signature, dependencies unchanged.
- Unified trace: 52 spans (hand-written) or 60 (graph) per alert instead of
  10 or 19, plus one gateway trace per call before.
- The `local-embed` path of the MCP server and the spans of the `mcp` SDK
  remain disjoint. Two candidates for a later ADR, not to be handled in
  `llm.py`.
- Every `gen_ai.*` aggregate carries a `resource.service.name` filter.
