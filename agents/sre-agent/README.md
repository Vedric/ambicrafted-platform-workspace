# Bounded SRE agent

Takes an alert, classifies it, searches the runbooks, produces a sourced
diagnostic, proposes actions. **Then it stops.** It never remediates, and
that is not a prompt instruction: none of the tools it has can change
anything.

Two implementations, same guardrails, same output contract:

| | `sre-agent` | `sre-agent-graph` |
|---|---|---|
| Module | `agent.py` | `graphe.py` |
| Orchestration | hand-written loop, 167 lines of code | LangGraph, 7 nodes, 452 lines |
| Extra dependencies | none | `--extra graphe`, 23 packages |
| Human approval gate | no | **yes, durable: survives `kill -9`** |
| State on disk | none | SQLite checkpoints, ~110 KiB per alert |
| Status | reference implementation | recommended for on-call |

Which to pick is settled by one question, and it is not about code style:
**does a human have to approve before the agent delivers, or must execution
survive the process?** If yes, the graph. If the caller is a machine in a
flow that does not stop, the loop; the checkpoints and the 23 packages are
pure liability there. The full measurement is in
[ADR 0004](../../docs/adr/0004-langgraph-vs-boucle-maison.md); the summary is
that orchestration gains 50 ms, and what you actually buy is durability of
state.

## Usage

```bash
# From a shell where direnv has loaded the workspace .env
uv run sre-agent "[CRITICAL] PostgreSQL: FATAL: sorry, too many clients already"
uv run sre-agent --json "..." | jq .
echo "$ALERTE" | uv run sre-agent
```

Exit codes: `0` complete analysis, `2` budget exhausted (human escalation
required), `3` execution error.

The graph adds a pause, and therefore a life cycle:

```bash
uv run --extra graphe sre-agent-graph "[CRITICAL] PostgreSQL: too many clients"
# → exit code 10, prints a thread id. The process may now die.
uv run --extra graphe sre-agent-graph --etat --thread-id ID
uv run --extra graphe sre-agent-graph --thread-id ID --reprendre oui
uv run --extra graphe sre-agent-graph --thread-id ID --reprendre "non, vérifier d'abord"
uv run --extra graphe sre-agent-graph --purger [--avant N] [--simulation]
```

Exit codes: `0` approved, `2` budget exhausted, `3` error, `4` refused by the
human, `10` awaiting approval.

## Processing chain

```
raw alert ──[ local, CONFIDENTIEL ]──> anonymised extract
                                              │
                      ═══ border ═══          │  only this form leaves
                                              │
               ──[ fast,  DERIVE ]──> triage ─┤
               ──[ smart, DERIVE ]──> tool loop ──> diagnostic
```

The triage step uses the `fast` alias, but on the extract, never on the
original alert: the compartmentalisation guardrail outranks the choice of
alias per step. See
[ADR 0003](../../docs/adr/0003-agent-sre-borne.md).

## The guardrails

Seven controls, each validated by a **refusal that was observed**, not
reasoned about. Two further controls exist that are not refusals and are
listed after the table rather than padded into it.

| # | Guardrail | Where it lives | How to check it |
|---|---|---|---|
| 1 | Tool-call budget, 10 | `budget.py` | `SRE_MAX_APPELS_OUTILS=2 uv run sre-agent "..."` → exit 2 |
| 2 | Monetary budget, 0.50 USD | `budget.py` | `SRE_MAX_COUT_USD=0.05 uv run sre-agent "..."` → exit 2 |
| 3 | Read-only | `outils.py` | `pytest -k liste_blanche`, closed allow-list of 4 tools |
| 4 | Compartmentalisation | `llm.py` | `pytest -k confidentielle`, refusal with no network access |
| 5 | Untrusted data confined | `prompts.py` | `pytest -k bloc`, per-run token |
| 6 | Source guard | `modeles.py` | `pytest -k source`, unsourced actions discarded |
| 7 | Durable human gate | `graphe.py` | `pytest -k porte`, silence is not approval |

```bash
uv run --extra graphe pytest        # 49 tests, no network required
```

All 49 run on an unplugged machine. That is the point: a guardrail that can
only be verified in real conditions is not a guardrail, it is an intention.

### 1 and 2. Budgets

A budget is not an instruction given to the model: it is a counter held by
the calling code, which the model can neither read nor modify. The tool
budget is decremented **before** execution: a refused call never reaches the
server. The monetary budget is charged afterwards, from the cost the gateway
reports: the agent holds no price table, which would force it to know a model
name anyway.

Both fail identically: stop, `budget épuisé, escalade humaine requise`, no
diagnostic. A partial diagnostic presented as complete would be more
dangerous than no diagnostic.

Design point: the tools stay declared to the model even when the budget is
spent. Removing them would make it answer without having consulted them, and
that degraded answer would be returned as a diagnostic.

In the graph, the same cap is opposed **by the routing edge**, so a burst of
three tools requested with two remaining is refused as a whole rather than
half-executed. Stricter, deliberately.

### 3. Read-only

There is no shell, no file write, no arbitrary HTTP. Not because a prompt
forbids it: because no function in this package exposes them to the model.
Security comes from the absence of the tool.

`OUTILS_AUTORISES` is a closed allow-list. A tool the MCP server might
publish without appearing there would never be presented to the model: adding
a tool is a decision of this repository, not a consequence of a server
update.

### 4. Compartmentalisation

Every LLM call goes through `appeler_llm`. There is therefore **one place**
to read to know whether client data can leave, and one to change to make that
no longer true. Three independent barriers:

1. **Application guard**: classification `CONFIDENTIEL` + a frontier alias
   raises `FuiteConfidentielle` before any network access.
2. **Virtual key**: a confidential payload travels with `CONFIDENTIAL_KEY`,
   restricted gateway-side to `local` and `local-embed`. The gateway answers
   403 if the first barrier fell.
3. **Gateway**: no fallback is configured out of `local`. A local error has
   no path to the frontier.

The MCP server's semantic search also embeds through `local-embed` with the
restricted key: the search query does not leave the machine either.

### 5. Untrusted data

The alert text and the runbook contents are never concatenated to an
instruction. They are wrapped by `prompts.bloc()`, between two markers
carrying a random token drawn once per run. The token is not cryptography: it
simply removes from the attacker the ability to write the closing marker,
since they cannot guess it.

The associated instruction is constant: what is inside a block is described,
not executed, and any instruction encountered is **reported** in a dedicated
field. The recorded hostile text stays local: it is not passed to the
frontier steps, only its count is.

### 6. Source guard

`Diagnostic.runbook_source` is nullable on purpose. A model required to give
a source invents one; a model allowed to declare it has none provides the
most useful line of the report. `appliquer_garde_source()` then removes the
unfounded actions from `actions_proposees`, moves them into
`actions_ecartees_sans_source`, and replaces them with a human escalation.
They stay visible: they simply stop being presented as procedures.

### 7. Durable human gate

Graph only. `porte_humaine` calls `interrupt()`: the complete state is
written to SQLite and the process hands back control **before** the diagnostic
is delivered. What is delivered has therefore never been delivered without a
human seeing it, and that property holds even if the machine stops during the
pause, demonstrated with `SIGKILL`, resumed in 1.28 s for 0 USD.

Silence is not approval: anything that is not an explicit agreement counts as
a refusal. A permissive default would turn the gate into a formality.

### The two that are not refusals

**Traceability** (`tracage.py`) is an observation control. One parent span
`task.incident_analysis` per run, each LLM call and each tool call as a child
span, with standard `gen_ai.*` attributes plus:

| Attribute | What it carries |
|---|---|
| `ambicrafted.data_classification` | `confidentiel` or `derive` |
| `ambicrafted.cost_usd` | cost of the span |
| `ambicrafted.task.type` | `incident_analysis`, `extraction`, `tool_call`… |
| `ambicrafted.gateway.alias` | the alias aimed at, never a model name |
| `ambicrafted.outcome` | `complete`, `budget_exhausted`, `error` |
| `ambicrafted.diagnostic.sourced` | whether the diagnostic cites a runbook |
| `ambicrafted.graph.path` | graph only: the nodes actually crossed |

Since [ADR 0005](../../docs/adr/0005-propagation-contexte-trace.md) the
gateway's own spans attach beneath the agent's, so one alert is one trace:
52 spans for the loop (10 agent + 42 gateway), 60 for the graph.

The trace id is printed at the end of the report. In Grafana
(`http://localhost:3000`): Explore → Tempo → TraceQL, for example
`{ resource.service.name = "sre-agent" }`. The `resource.` prefix is
mandatory; without it the query silently matches nothing.

**Tracing never fails the agent.** If Tempo is unreachable, the export fails
in its background thread and the analysis continues. That is deliberate, and
it is also a trap: a successful run with a printed trace id proves nothing
about whether the trace was stored. The only valid check is to go and fetch
it, see
[`docs/OPERATIONS.md`](../../docs/OPERATIONS.md#traces-are-not-arriving-in-tempo).

**Deserialisation allow-list** (`graphe.py`) closes a surface the framework
opened: `TYPES_PERSISTABLES` with `pickle_fallback=False` restricts what the
SQLite checkpoint may rebuild to four named types. It is a real control, but
no test currently exercises its refusal, stated here rather than claimed.

## The output contract

```python
class Diagnostic(BaseModel):
    cause_probable: str
    confiance: Confiance                # haute | moyenne | faible
    elements_manquants: list[str]
    actions_proposees: list[str]
    runbook_source: str | None          # nullable, on purpose
```

The agent actually returns a `Rapport`, which wraps the diagnostic in its
conditions: which tools were called, what the budget allowed, what the code
refused. The diagnostic alone is unverifiable; what surrounds it is what
makes it auditable.

## Configuration

Every variable is optional except the keys, which come from the workspace
`.env` loaded by direnv.

| Variable | Default | Role |
|---|---|---|
| `CONFIDENTIAL_KEY` | none | virtual key restricted to `local` and `local-embed` |
| `ORCHESTRATOR_KEY` | none | key for derived payloads |
| `SRE_MAX_APPELS_OUTILS` | `10` | guardrail 1 |
| `SRE_MAX_COUT_USD` | `0.50` | guardrail 2 |
| `SRE_MAX_TOURS` | `12` | cap on loop turns |
| `SRE_ALIAS_RAISONNEMENT` | `smart` | alias for the final reasoning, see below |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://127.0.0.1:4318` | Tempo's OTLP/HTTP receiver |
| `SRE_TRACAGE` | `1` | `0` disables the export |
| `SRE_DEBUG_MCP` | none | lets the MCP server's stderr through |
| `SRE_CHECKPOINT_DB` | `~/.local/state/sre-agent/graphe.sqlite` | graph only |
| `SRE_RETENTION_JOURS` | `14` | graph only, purge window |

**Local reasoning.** `SRE_ALIAS_RAISONNEMENT=local` moves the tool loop onto
the local model: verified; it drives the tool loop, finds the runbook and
produces a sourced diagnostic, for about 0.001 USD instead of 0.20. The
triage step stays on `fast`; it only ever sees derived data, but it does
reach the frontier. A strictly offline mission would need that step moved
too, which is not exposed today.

**Tempo's address.** Compose publishes Tempo's OTLP/HTTP receiver on
`127.0.0.1:4318`, and that is the default. Never put a container address here:
they are assigned in start order and change at the first `docker compose up`
that recreates a container, which is exactly how this default previously came
to point at Grafana instead of Tempo, silently.

## What this agent does not do

- It does not remediate, and cannot: it has no write tool.
- It does not invent procedures. Outside the corpus, it says so and
  escalates.
- It does not degrade silently: when the budget is exhausted, there is no
  half-diagnostic.
- It knows no provider model name, only aliases.
