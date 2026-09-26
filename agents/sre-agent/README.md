# Bounded SRE agent

The `sre-agent` loop and `sre-agent-graph` graph share the same local transport,
budgets, MCP allow-list, prompts and source guard. Neither executes remediation.

## Run

Load the root `.env` through direnv, synchronize the projects, and index the
runbooks before using semantic search:

```sh
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

The source registry is populated only by complete verified MCP reads. Actions
must match passages actually read from the cited document. A missing source,
failed/truncated read or invented/paraphrased action causes rejection and an
explicit gap/escalation. Provenance does not prove operational relevance.

The graph's approval request includes missing evidence and reported injections.
Pending/rejected reports have `diagnostic=null`. A structured API decision
requires `{"approuve": true}` with a boolean. A string value such as `"false"`
never approves. CLI text accepts explicit affirmative tokens; other text refuses.

## Limits and configuration

| Setting | Default |
|---|---:|
| `SRE_MAX_APPELS_OUTILS` | 10 |
| `SRE_MAX_TOURS` | 12; final answer on the last turn is accepted |
| `SRE_MAX_COUT_USD` | 0.50; local inference has no gateway monetary charge |
| `SRE_MAX_DUREE_S` | 1800 per invocation, excluding human waiting |
| `SRE_TIMEOUT_LLM_S` | 300 per request boundary |
| Alert size / context size | 20,000 / 100,000 characters |
| Tool response | 12,000 characters |
| `QDRANT_COLLECTION` | `runbooks-current` |

Limits are checked before work and at response boundaries. Starting/stopping
subprocesses and timed-out I/O may add cleanup time. Costs must be finite and
non-negative. An external transport call with unknown cost stops explicitly.

Source installs derive the repository root from the module location. For an
installed wheel used elsewhere, set `SRE_RACINE_DEPOT` to the checkout containing
the MCP project and runbooks. The wheel does not bundle the MCP server.

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
