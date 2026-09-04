# Architecture Decision Records

Every architecture decision in this platform is recorded here (rule 5 of
[`CLAUDE.md`](../../CLAUDE.md)). An ADR is a **dated document that freezes a
decision** in the state of knowledge of its day: it is not updated when
reality moves on. When a decision is superseded, a new ADR says so and the
old one stays as it was written.

File names are kept in French, like every other identifier in this repository
— see the language policy in [`CONTRIBUTING.md`](../../CONTRIBUTING.md).

| # | Title | Status | Date | In one line |
|---|---|---|---|---|
| [0001](0001-litellm-passerelle-unique.md) | LiteLLM as the single gateway | Accepted, in local production | 2026-08-24 | One OpenAI-compatible entry point, semantic aliases, virtual keys, and no fallback out of `local`. |
| [0002](0002-recherche-semantique-runbooks.md) | Semantic search over the runbooks (Qdrant + MCP) | Accepted, in local service | 2026-08-25 | Chunk by markdown section rather than by character count, because a fragment of a procedure looks complete and is dangerous. |
| [0003](0003-agent-sre-borne.md) | Bounded SRE agent, without a framework | Accepted, in local service | 2026-08-25 | A hand-written loop, because the hundred lines it occupies are exactly the lines where the guardrails are decided. |
| [0004](0004-langgraph-vs-boucle-maison.md) | LangGraph against the hand-written loop | Accepted — both coexist, `agent.py` is the reference | 2026-08-25 | Measured: orchestration gains 50 ms and costs 23 packages; what you actually buy is a pause that survives `kill -9`. |
| [0005](0005-propagation-contexte-trace.md) | Propagation of the trace context to the gateway | Accepted | 2026-08-25 | One `traceparent` header turns two disjoint traces per call into a single 52-span trace per alert. |
| [0006](0006-stack-passerelle-dans-le-depot.md) | The gateway stack lives in the repository | Accepted | 2026-08-25 | The most critical layer existed only on disk; a clone plus a `.env` must be enough to rebuild it. |
| [0007](0007-secret-fuite-par-la-sortie.md) | A secret leaks through a command's output | Accepted | 2026-08-27 | The incident that rotated four secrets: nothing was written anywhere, the values were merely printed. |
| [0008](0008-diff-indexe-vers-l-api-gitguardian.md) | The staged diff goes to GitGuardian's API | Accepted | 2026-09-04 | An outbound flow accepted because GitGuardian already reads the pushed repository — written down with the two conditions that would take that argument away. |

## Reading order

- **Starting from scratch**: 0001 (the gateway), then 0003 (the agent), then
  0002 (the RAG pipeline).
- **Interested in the security argument**: 0003, then 0007, then 0008, then
  [`SECURITY.md`](../../SECURITY.md). 0007 and 0008 read together are the
  point: the first says no hook can see a command's output, the second adds a
  hook that does not change that and says what it does instead.
- **Interested in the framework question**: 0004 alone answers it, with
  figures.
- **Interested in observability**: 0005, which also documents the two
  aggregation traps of the unified trace.

## Writing a new one

`docs/adr/NNNN-titre-en-francais.md`, next free number, and the sections used
throughout this series: Context, Decision, Alternatives rejected,
Consequences. A "Consequences" section that lists only benefits has not been
written honestly; every ADR here names what its decision costs.

State what was **verified**, and how. A consequence that has not been
observed is written as a prediction, not as a result.
