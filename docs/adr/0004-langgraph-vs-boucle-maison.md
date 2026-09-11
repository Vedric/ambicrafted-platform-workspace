# ADR 0004: LangGraph against the hand-written loop

Status: accepted, both implementations coexist, `agent.py` remains the
reference, `graphe.py` becomes the recommended path for on-call
Date: 2026-08-25
Completes ADR 0003, which announced this port as a later step.

## Context

ADR 0003 established that an agent framework must not be entrusted with the
guardrails, and kept the comparison for later. It is now done.

The port was carried out under a single constraint: `llm.py`, `outils.py`,
`prompts.py`, `budget.py`, `tracage.py` are imported as they are by
`graphe.py`, without a single modified line. Same compartmentalisation, same
allow-list, same token confinement, same budgets. What differs is
orchestration, and nothing else, a condition without which the figures below
would only measure a rewrite.

Verification: the 23 guardrail tests of ADR 0003 pass unmodified, and 14
additional tests replay the same properties through the graph.

## Measurements

Identical alert for every run: `PostgreSQL: too many clients already`, corpus
of two runbooks, local model preloaded, gateway and Qdrant warm. Three runs
per implementation.

### Code

|                                              | hand-written | graph |
|----------------------------------------------|-------------:|------:|
| Total lines (orchestration + CLI)             |          406 |   966 |
| Lines of code (excl. blank, comment, docstring) | 266        |   576 |
| of which orchestration alone                  |          167 |   452 |
| Shared guardrails, not rewritten              |        1,151 | 1,151 |

The graph is 2.7 times the code volume of the loop. The breakdown matters
more than the total:

| Item in `graphe.py`                             | ~lines | Nature |
|-------------------------------------------------|-------:|--------|
| Typed state, reducers, budget replay             |     85 | price of serialisability |
| Span context and tool session carried by the process | 25 | price of crossing the process boundary |
| Node decorator (span, errors put into state)     |     50 | factoring out what is inline in `analyser()` |
| The seven nodes                                  |    210 | equivalent of `_extraire`/`_trier`/`_raisonner` |
| Conditional edges                                |     60 | **new capability** |
| Assembly, checkpointer, deserialisation allow-list | 80   | **new capability** |
| Three entry points instead of one                |    155 | **new capability** |

About 220 lines fund capabilities the loop does not have, and 110 lines are
the framework's entry price: state serialisability and the loss of process
context.

### Dependencies

|                                     | hand-written | graph |
|-------------------------------------|-------------:|------:|
| Declared dependencies                |            5 |   5+2 |
| Packages actually installed on top   |            0 |    23 |

Two declarations, `langgraph>=1.2,<2` and
`langgraph-checkpoint-sqlite>=3.1,<4`, pull twenty-three packages. They are
isolated in the `[project.optional-dependencies] graphe` extra, so that
`uv sync` without the extra yields exactly the version of ADR 0003.

Two of those packages deserve to be named, because they contradict a project
rule and no version of LangGraph makes it possible to avoid them:

- **`langchain-core`** is a hard dependency of `langgraph`. None of its
  abstractions is used here: no `ChatModel`, no `tool`, no chain. Our calls go
  through `llm.appeler_llm`, our tools through `outils.executer_outil`. The
  package is present, it is not used.
- **`langsmith`** is a hard dependency of `langchain-core`. It is not
  adopted: tracing stays OpenTelemetry to Tempo, and `LANGSMITH_TRACING=false`
  is set explicitly. Without an API key it is inert, but this is a dependency
  that by default seeks to export telemetry off the machine. To be watched at
  every version bump.

### Time, on the same alert

|                        | hand 1 | hand 2 | hand 3 | mean |
|------------------------|-------:|-------:|-------:|-----:|
| Total                  | 58.15 s | 62.66 s | 62.00 s | 60.94 s |
| of which LLM calls     | 55.73 s | 60.20 s | 59.64 s | 58.52 s |
| of which MCP tools     |  0.14 s |  0.18 s |  0.04 s |  0.12 s |
| **of which orchestration** | **1.50 s** | **1.51 s** | **1.44 s** | **1.48 s** |

|                        | graph 1 | graph 2 | graph 3 | mean |
|------------------------|--------:|--------:|--------:|-----:|
| Up to the gate         | 60.86 s | 69.54 s | 70.11 s | 66.84 s |
| Resume after approval  |  1.28 s |  1.37 s |  1.54 s |  1.40 s |
| Total                  | 62.14 s | 70.91 s | 71.65 s | 68.23 s |
| of which LLM calls     | 58.09 s | 66.72 s | 66.94 s | 63.92 s |
| of which MCP tools     |  0.13 s |  0.12 s |  0.13 s |  0.13 s |
| **of which orchestration** | **1.46 s** | **1.43 s** | **1.70 s** | **1.53 s** |

The naive reading, "the graph is 12% slower", is wrong. The orchestration
durations, obtained by subtracting from the parent span the sum of the
`llm.*` and `tool.*` spans, are **1.48 s against 1.53 s**, that is **50 ms of
overhead**, checkpoint writes included (eleven per alert). The seven-second
gap on the total is generation variance: both implementations issue the same
number of LLM calls (5) on the same alert, and the ranges of LLM durations
overlap.

The only deterministic overhead is at import:

| Import                    | median |
|---------------------------|-------:|
| Bare Python               |  13 ms |
| `+ sre_agent.agent`       | 767 ms |
| `+ sre_agent.graphe`      | 1,079 ms |

**Total cost of the framework: about 360 ms per alert** (312 ms of import,
50 ms of orchestration) on a task that takes 60,000. That is 0.6%.

### Money

|                 | run 1 | run 2 | run 3 | mean |
|-----------------|------:|------:|------:|-----:|
| hand-written    | 0.2560 | 0.2722 | 0.2123 | 0.2468 USD |
| graph           | 0.2494 | 0.2657 | 0.2520 | 0.2557 USD |
| graph, resume   | 0.0000 | 0.0000 | 0.0000 | 0.0000 USD |

The ranges overlap widely (hand-written 0.212–0.272; graph 0.249–0.266).
**The port costs nothing in money**: same prompts, same aliases, same number
of calls. Resuming after approval costs exactly zero, which is the point: the
human wait replays nothing.

### Persistent state

|                                | hand-written | graph |
|--------------------------------|-------------:|------:|
| Checkpoints per alert           |            0 |    11 |
| On-disk volume per alert        |            0 | ~110 KiB |

## What each can do that the other cannot

### The hand-written loop alone

- **Start with no state on disk.** No persistent file, therefore no
  deserialisation surface, no alert-derived data surviving the process, no
  retention to manage.
- **Be read in one pass.** The flow is a sequence of statements in a single
  file of 167 lines of code. The graph requires reading the nodes, then the
  edges, then the assembly, to reconstitute the same flow.
- **Add no unused dependency**: neither `langchain-core` nor `langsmith`.
- **Start in 767 ms** instead of 1,079.

### The graph alone

- **Pause durably before delivering.** `porte_humaine` calls `interrupt()`,
  the complete state is written to SQLite, the process hands back control.
  Demonstrated: the process was SIGKILLed during the pause; a fresh process,
  with the same `thread_id` and `Command(resume="oui")`, delivered the
  diagnostic in 1.28 s for 0 USD, budget and tool history intact. The
  hand-written loop cannot do this, and cannot learn to without rewriting
  itself around a serialisable state, that is, without becoming a graph.
- **Resume in the middle, not only at the gate.** The eleven checkpoints
  cover every super-step. An interruption during reasoning resumes at the
  last node crossed, without replaying calls already paid for.
- **Make the execution path a piece of data.** `journal` in the state,
  `ambicrafted.graph.path` on the parent span. In a post-mortem you read
  `extraction → classification → raisonnement → recherche_runbooks →
  raisonnement → abandon` without re-reading code or cross-checking logs.
- **Make budget decisions testable without executing.** The edges are pure
  functions of the state. `apres_raisonnement({...})` is tested in one line;
  the hand-written equivalent is an `if` in the middle of a loop that is only
  reached by unrolling everything before it.
- **Make the finalisation retry observable.** It is an edge crossing
  `diagnostic → raisonnement`, visible in the trace and in the journal,
  instead of an `except` invisible from the outside.

## Decisions

### SQLite checkpointer, not Postgres

A local file, `~/.local/state/sre-agent/graphe.sqlite`, in 0600 inside a 0700
directory.

Postgres was available: the gateway has one. It was rejected. Making an
on-call agent's resume capability depend on the database that holds the
gateway's accounting creates a coupling between two unrelated concerns: an
agent that can no longer resume because billing is under maintenance. The
agent is moreover single-machine: a `thread_id` is resumed on the machine
that created it.

The permissions are not decoration: the checkpoint contains the `Extraction`,
therefore data derived from a client alert, and it survives the process. A
persistent state readable by the whole system would cancel part of the
benefit of ADR 0003's compartmentalisation.

**Evolution path towards Postgres.** Three conditions, all to be met:

1. Several executors: a scheduler, or resumes from a machine other than the
   one that started the analysis. As long as a `thread_id` stays attached to
   its machine, SQLite is enough.
2. A retention policy to enforce: checkpoints contain derived data, therefore
   a purge policy. A local file is purged with `rm`; a shared database calls
   for a written decision.
3. An instance distinct from `litellm-db`. The coupling refused here must not
   be reintroduced through the back door.

The change would then reduce to `PostgresSaver` in place of `SqliteSaver` in
`compiler()`, plus migrating the file. The rest of `graphe.py` is indifferent
to the backing store. That is the only place in the module that knows about
SQLite.

### A deserialisation allow-list, added

The port introduces a trust boundary the loop did not have: a persistent file
that the graph re-reads and deserialises. By default LangGraph accepts any
Python type there, which its own documentation flags as a code-execution
vector for whoever can write into that file, and it emits a warning
announcing the block in a future version.

`TYPES_PERSISTABLES` closes that with the same figure as `OUTILS_AUTORISES`:
four named types, `pickle_fallback=False`, a list held by this repository.
This is not the modification of an existing guardrail, it is one more
guardrail, made necessary by the framework and to be charged to its
liabilities.

### Two behavioural differences, accepted, both stricter

1. **The tool budget is opposed by the edge, therefore before the node.**
   A burst of three tools requested when only two remain is refused as a
   whole; the hand-written loop would have executed two before raising.
   Verified in execution: `SRE_MAX_APPELS_OUTILS=2` routes to `abandon`, exit
   code 2, no exception raised, no tool from the refused burst reaches the
   server. `executer_outil` stays in place and remains authoritative if the
   edge let something through.
2. **The finalisation retry is an edge.** Same uniqueness, a single pass
   that `relance_tentee` attests to, but it becomes observable.

### The `abandon` node attributes the reason

Defect found during the demonstration and fixed: the node announced the turn
cap whatever cap was actually reached, because the routing edge does not say
why it routes. `_motif_abandon()` replays the conditions and names the right
cap. "Tool cap" and "turn cap" call for opposite corrections, and nobody will
go and re-read the graph at 3 a.m. to decide.

This is a cost of the declarative model: separating the decision from its
explanation creates a place where the two can diverge.

## Tracing: what was verified, and what was found

The fear was that LangGraph would introduce a competing generation of
`gen_ai.*` attributes next to that of `tracage.py`. Verification was done on
the spans actually stored in Tempo, not on the documentation.

**LangGraph emits nothing.** No OpenTelemetry dependency in `langgraph`,
`langchain-core` or `langgraph-checkpoint`. No span carrying `langgraph`,
`langchain` or `chain` in Tempo. Only two services write there: `sre-agent`
and `litellm-gateway`. The port does not add a single line of unwanted
telemetry.

**The coexistence of generations does exist, but it predates the port** and
comes from the gateway:

| Emitter | Attributes |
|---|---|
| `sre-agent` (`llm.py`) | `gen_ai.operation.name`, `gen_ai.request.max_tokens`, `gen_ai.request.temperature`, `gen_ai.response.finish_reasons`, `gen_ai.response.tool_calls` |
| `litellm-gateway` | `gen_ai.cost.*` (11 attributes, in no version of the OTel semantics), `gen_ai.usage.total_tokens`, `gen_ai.response.id`, `gen_ai.openai.response.service_tier`, `litellm.*`, `llm.is_streaming`, `call_type`, `model_id` |
| **both, with different meanings** | `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.system`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` |

The conflict is on the five shared keys. Our `gen_ai.request.model` carries
**the alias** (`smart`, `local`); the gateway's carries **the resolved model**
(`nomic-embed-text`, with `litellm.provider.model` at
`ollama/nomic-embed-text`). A Grafana query on `gen_ai.request.model`
therefore returns a mix of aliases and provider names depending on which
service is hit.

Two consequences, outside the scope of this ADR but to be handled:

- Rule 1 of CLAUDE.md, no provider model name in the code, is respected by
  our code, but provider names arrive in Tempo through the gateway's own
  telemetry. A dashboard must filter on `resource.service.name` if it wants
  to reason in aliases.
- The two trees are **disjoint**: no `trace_id` overlap between our traces and
  those of `litellm-gateway`, for lack of a `traceparent` header propagated
  by `llm.py`. An LLM call therefore produces two unrelated traces. Joining
  them would require injecting the context into the HTTP headers,
  a modification of `llm.py`, therefore of a guardrail: outside the scope of
  this port, to be decided separately.

### Does the trace survive the death of the process?

No, and one must not pretend otherwise: a parent span dies with its process.
The graph therefore opens a new trace on resume and links it explicitly to
the old one, through an OTel `Link` and through
`ambicrafted.resume.of_trace_id`. Verified: the resume trace (2 spans,
103 ms) carries a link to the trace from before the SIGKILL (19 spans,
58.3 s), together with the complete path of the nine nodes re-read from the
checkpoint. Grafana displays the two halves of one story.

Structure obtained, consistent with ADR 0003: one parent span
`task.incident_analysis`, each node as a child span `node.*`, each LLM call
and each tool as a grandchild `llm.*` / `tool.*`.

## Recommendation

**Take the graph when a human must validate before the agent delivers, or
when execution must survive the process.** That is the only criterion that
decides. A durable approval gate is not added to a loop: it presupposes a
serialisable state and a resume point, that is, a graph. For 360 ms and 23
packages, you get a pause that neither a restart, nor a deployment, nor a
`kill -9` erases. On an on-call agent whose output will be executed by
someone tired, this is the guardrail that ADR 0003 was missing: all the
others bound what the agent does, this one bounds what it earns the right to
hand over.

**Take the hand-written loop when the agent is called by a machine, in a flow
that does not get interrupted**: alert enrichment, automatic triage, batch
processing. There is then nobody to cross the gate, persistence serves no
purpose, and the 23 packages and the state file are pure liability: two more
unused dependencies, one more deserialisation surface, one retention policy
to hold.

**Do not take a framework for orchestration.** That is the sharpest result of
the measurement: the orchestration gain is nil (50 ms) and the cost in
reading is real: 452 lines of code against 167 for the same flow. A
seven-node graph is not read faster than a hundred-line loop, it is read
slower, in three places instead of one. What you buy is not clarity of flow,
it is durability of state.

**Never entrust it with the guardrails.** The port held the constraint, and
that is what makes these figures legible: compartmentalisation, allow-list,
token confinement, budgets and source guard all went through without a
modified line. Verified in the graph, on an unplugged machine: a confidential
payload directed at `smart` raises `FuiteConfidentielle`, no network call is
attempted, the cost incurred is nil and the message is identical to that of
the hand-written loop. The only thing the framework required is one more
guardrail, the deserialisation allow-list, to close a surface it had opened
itself. That is the right division: the framework holds the state, this
repository holds the rules.

## Consequences

Verified in execution:
- PostgreSQL alert: stop on `interrupt()`, exit code 10, diagnostic sourced
  on `incident-p1-database.md`, 3 to 4 tools, ~0.25 USD.
- SIGKILL during the pause: no line written afterwards, resume by a fresh
  process in 1.28 s for 0 USD, context intact.
- `SRE_MAX_APPELS_OUTILS=2`: routes to `abandon`, exit code 2, exact reason,
  no exception, no partial diagnostic.
- Compartmentalisation subverted: `FuiteConfidentielle`, zero network calls,
  zero cost, behaviour identical to the hand-written loop.
- Trace: 1 parent span, 9 node spans, 19 spans in total; resume trace linked
  to the previous one.
- 37 tests without network: the original 23 unchanged, 14 new.

Accepted costs and limits:
- 23 packages, including `langchain-core` and `langsmith`, present and
  unused. To be re-examined at every major version bump of `langgraph`,
  bounded to `>=1.2,<2`.
- Checkpoint retention: `sre-agent-graph --purger --avant N` deletes threads
  with no activity for N days (default 14, matching Tempo's 336 h retention:
  a thread and its trace expire together) then runs VACUUM and truncates the
  WAL. Manual or cron; nothing triggers it automatically.
- Two implementations to maintain. `graphe.py` imports its token caps and two
  decoding functions from `agent.py`: divergence of settings is prevented by
  construction, not by discipline.
- The abandonment reason is reconstituted by the node from the state, and not
  transmitted by the edge that decided. That is a place where decision and
  explanation can diverge; a test locks the attribution.

## Alternatives rejected

- **Rewriting the hand-written loop to add a pause.** That means writing a
  checkpointer, a serialisable state format and a resume path, that is, a
  graph, less well reviewed. The framework justifies itself precisely there.
- **`interrupt_before` on a node rather than `interrupt()` inside the node.**
  The interruption would be decided at compile time rather than by the node's
  code, which would forbid composing the approval request from the
  diagnostic. A human who approves must see what they approve.
- **The in-memory checkpointer for the demonstration.** It would have made
  the demonstration false: surviving `kill -9` is the whole subject.
- **Adopting LangSmith, present anyway.** Telemetry leaves the machine; Tempo
  is local and already in service. Rule 2 of CLAUDE.md does not distinguish
  data from metadata about data.
