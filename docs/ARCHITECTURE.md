# Architecture

The workstation hosts a six-service gateway/observability stack, local Ollama,
a runbook corpus, an MCP server, and two implementations of one read-only
incident-analysis workflow. The shared UI/CLI control API and local speech runtime
are described in ADR 0010–0011; incident guarantees are in ADR 0009. Older ADRs
remain historical records.

## Incident path

1. An input-size/configuration check runs before model work.
2. `local` extracts a technical description. The description remains confidential.
3. `local` classifies urgency and actionability.
4. `local` reasons with four MCP tools: list, read, literal search and semantic search.
5. The source guard checks actions against passages in a complete, verified
   `read_runbook` result. A filename supplied by a model is insufficient.
6. The loop returns a proposal. The graph persists the proposal and pauses
   for a human; only approval creates a delivered diagnostic.

Every model call uses `llm.appeler_llm`. Every model tool invocation uses
`outils.executer_outil`. The model cannot mutate counters, provenance or
approval state by writing JSON fields with those names.

The shared transport still supports explicitly classified public/derived
calls for separate uses, but no SRE stage invokes that external path.

## State lifecycle

A new incident needs a new thread ID. Reuse is refused; resume requires an
existing human interruption. The raw alert is held only in the invocation
context, so a process crash before extraction requires a new input. Extracts,
reasoning messages and tool results are persisted and treated as confidential.

Public graph helpers open/close SQLite connections and hold an exclusive
advisory lock during database operations. A second concurrent invocation on
the same database receives an explicit error. One graph invocation per
process is supported; separate processes share the locked database.

Only the named model types are permitted by the checkpoint serializer and
pickle fallback is disabled. Unknown types cannot silently become executable
objects. This does not make an attacker-writable database trustworthy.

## Retrieval lifecycle

The corpus consists of local Markdown procedures that require service-owner
review before operational reliance. The indexer chunks by heading,
validates embedding indices, dimensions and finite values, writes a fresh
physical collection and checks its count. A single alias update publishes it.
Previous collections are retained for rollback, including on an ambiguous
network failure during publication. Operators explicitly clean unused versions.

`runbooks-current` is the default alias. An existing physical collection named
`runbooks` is preserved during migration. A requested alias that conflicts with
a physical collection is refused rather than deleting that collection.

Each point carries a corpus hash. Semantic search compares it with the current
files and refuses stale results. The 0.60 similarity threshold is not a relevance guarantee. Qualification found
both a false positive and a false negative; see
[measured evaluation limits](../evals/RESULTS-2026-09-26.md).
Literal search remains available if embeddings or Qdrant fail.

A `read_runbook` result includes filename, text, SHA-256 and truncation status.
Only untruncated envelopes populate the agent's source registry. Accepted
proposals are verbatim passages after whitespace normalization. Operators
must verify the incident match and any necessary context.

## Observability

W3C context links agent model calls to the gateway. The root is
`task.incident_analysis`; graph nodes and tool calls have separate spans.
An expected human interruption does not mark its node as an error.

| Attribute | Meaning | Aggregation |
|---|---|---|
| `ambicrafted.cost_usd` | Individual LLM call cost | Sum agent LLM spans only |
| `ambicrafted.run.cost_usd` | Run total | Read one root per run; do not sum a resumed total again |
| `ambicrafted.budget.spent_usd` | Cumulative snapshot | Never sum |

Gateway spans may carry their own accounting. Filtering by service and span
kind is necessary. A resume links to the original trace and creates no new
LLM work when the human gate is the only pending step.

Prometheus scrapes itself, Tempo, Qdrant and Grafana. Docker healthchecks cover
five services; Tempo's shell-free image is checked through HTTP metrics and
readiness from outside its container. Grafana provisions a platform dashboard.
Availability alerts stay local; no external notification destination is set.

## Deliberately bounded scope

SQLite is incident state, not cross-customer conversational memory. Qdrant is
document retrieval, not an execution planner. No use case currently requires
Neo4j or another long-lived memory service. Introducing one requires an
explicit graph query/use case, data partitioning and deletion design.

This is a workstation architecture. Host availability, disk capacity and
model latency remain operational constraints; it has no multi-host failover.
