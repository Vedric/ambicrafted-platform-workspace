# Bounded SRE agent

The `sre-agent` loop and `sre-agent-graph` graph share the same local transport,
budgets, MCP allow-list, prompts and source guard. Neither executes remediation.

## Run

Load the root `.env` through direnv, synchronize the projects, and index the
runbooks before using semantic search:

```sh
uv sync --locked --project ../../mcp-servers/runbooks
uv sync --locked --project ../../apps/control-api
uv sync --locked --extra graphe
uv run --locked sre-agent 'synthetic alert' --json
uv run --locked --extra graphe sre-agent-graph 'synthetic alert' --json
uv run --locked --extra graphe sre-agent-graph --thread-id ID --etat
uv run --locked --extra graphe sre-agent-graph --thread-id ID --reprendre oui
```

Use a custom `--checkpoints` path consistently on every graph operation. The
printed resume commands preserve it. Management modes are mutually exclusive.
A new incident must use a new thread; a completed/rejected thread cannot be
resumed as if it were a fresh approval.

| Exit | Meaning |
|---:|---|
| 0 | Complete proposal (loop), or approved diagnosis (graph) |
| 2 | Budget exhausted; no diagnosis |
| 3 | Execution/configuration error |
| 4 | Human rejection; no delivered diagnosis |
| 10 | Human approval pending; proposal is in the approval request |

## Safety contract

Extraction, triage and reasoning all use `local` with confidential
classification. `SRE_ALIAS_RAISONNEMENT=smart` is rejected. An extraction may
retain identifying data and is never automatically declassified.

Extraction and triage request JSON Schema generation and still validate the
received response. Reasoning receives original observations in a temporary
per-call message so it can challenge the derived summary. That added message is
not stored in checkpoints or trace attributes; generated text can nevertheless
repeat its contents and remains confidential. These controls constrain shape
and routing, not factual correctness. The
[real qualification protocol](../../evals/qualification/README.md) separates
mechanical contracts from substantive review.

The source registry is populated only by complete verified MCP reads. Actions
must match passages actually read from the cited document. A missing source,
failed/truncated read or invented/paraphrased action causes rejection and an
explicit gap/escalation. Provenance does not prove operational relevance.

After at least one verified complete read, two consecutive tool turns without a
new filename/content-hash pair stop further exploration. One structured local
finalisation uses the original observations and acquired sources, with no tools
or model-supplied quality evidence. It remains inside the existing budgets and
passes the same source guard and consistency review. New source versions reset
this counter; search snippets and repeated old versions do not. This can stop a
useful search early and does not establish completeness. See
[ADR 0043](../../docs/adr/0043-arret-recherche-sans-progres.md).

A final **AI consistency review** makes at most one additional local call under
the same budget. It can reject a materially inconsistent proposal or lower its
confidence, but cannot add or rewrite actions. Literal-source arithmetic uses
code with explicit units; its results and review token/latency overhead appear
in `diagnostic.qualite` (also in the pending approval request). Missing evidence,
an invalid/unavailable review or a contradicted calculation leads to explicit
abstention with no actions. A budget overrun still stops the analysis.

This is a fallible review by the same model, not independent verification.
Correct arithmetic does not prove that the selected populations are comparable,
or establish causality. Previously read evaluation cases are regressions.
See [ADR 0041](../../docs/adr/0041-revue-coherence-agent-bornee.md) for supported
operations, refusal conditions and qualification requirements.

The graph's approval request includes missing evidence and reported injections.
Pending/rejected reports have `diagnostic=null`. A structured API decision
requires `{"approuve": true}` with a boolean. A string value such as `"false"`
never approves. CLI text accepts explicit affirmative tokens; other text refuses.

## Limits and configuration

| Setting | Default |
|---|---:|
| `SRE_MAX_APPELS_OUTILS` | 10 |
| `SRE_MAX_TOURS` | 12; final answer on the last turn is accepted |
| `SRE_MAX_COUT_USD` | 0.50 of reported API cost; absent local headers remain unknown |
| `SRE_MAX_TOKENS_TOTAL` | 60,000 observed tokens; allowed range 1–1,000,000 |
| Completion cap | At most 6,000 tokens per request |
| `SRE_MAX_DUREE_S` | 1800 per invocation, excluding human waiting |
| `SRE_TIMEOUT_LLM_S` | 300 for the complete HTTP exchange, capped by the run's remaining deadline |
| Alert size / context size | 20,000 / 100,000 characters |
| Tool response | 12,000 characters |
| `QDRANT_COLLECTION` | `runbooks-current` |

Limits are checked before work and at response boundaries. Starting/stopping
subprocesses and timed-out I/O may add cleanup time. Costs must be finite and
non-negative. An external transport call with unknown cost stops explicitly.
An absolute asynchronous HTTP deadline prevents periodically received bytes from
extending a request indefinitely. Cancellation closes the client before returning;
when embedded in an existing event loop, a joined worker preserves the synchronous
API. A disconnected proxy does not prove that upstream model inference has stopped.
The token ceiling uses actual provider counters, not a tokenizer estimate; the
last response can overshoot before the run stops. Partial usage is a lower bound
and absent usage is unknown, not zero. Reports distinguish attempted calls,
complete token measurements and API-cost coverage. Hardware and electricity
costs are not measured. See [NEXUS and usage contracts](../../docs/MCP-GATEWAY.md).

Source installs derive the repository root from the module location. For an
installed wheel used elsewhere, set `SRE_RACINE_DEPOT` to the checkout containing
the control-API gateway project, MCP backend and runbooks. The wheel does not
bundle these services. The MCP client always selects the NEXUS runbooks profile;
control-plane tools are not added to the model prompt.

## Persistence and retention

The default database is `~/.local/state/sre-agent/graphe.sqlite`. The raw alert
is not a checkpoint field; derived text, injections, messages and read passages
are confidential and are persisted. The file is private; existing parent
permissions are checked without being changed. Public helpers close connections.

```sh
uv run --locked --extra graphe sre-agent-graph --purger --simulation
uv run --locked --extra graphe sre-agent-graph --purger --avant 14
```

Daily scheduling, backups and restore verification are described in
[Operations](../../docs/OPERATIONS.md). Old checkpoints written by earlier
versions may still contain raw alerts until their retention expires.

Checkpoint contract version 3 refuses approval of older pending proposals that
never passed the consistency review. Their history remains readable with `--etat`;
restart the analysis with a new thread instead of deleting or migrating the old
checkpoint. Inventory pending analyses before upgrading a running installation.
The control API also records the contract version in code-owned options for new
analyses. Its `reprise_compatible` capability prevents a legacy decision before
changing history or queueing work. Missing/old markers require a new analysis and
the original input supplied again by the user; they are never silently upgraded.

## Development

```sh
uv sync --locked --extra graphe
uv run --no-sync pytest -q
uv run --no-sync mypy
uv run --no-sync ruff check .
uv run --no-sync coverage run -m pytest -q
uv run --no-sync coverage report
uv build
```

Tests simulate failures at boundaries and block network connections. Real model
quality is evaluated separately; unit-test success is not a quality score.
