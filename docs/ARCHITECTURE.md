# Architecture

The workstation hosts a six-service gateway/observability stack, local Ollama,
a runbook corpus, two stdio MCP servers, and two implementations of one read-only
incident-analysis workflow. The shared UI/CLI control API and local speech runtime
are described in ADR 0010–0015; incident guarantees are in ADR 0009. Older ADRs
remain historical records.

## Operator workspace and control boundary

The React console and unified CLI use one authenticated FastAPI control service
on `127.0.0.1:8787`. The workspace includes overview, missions, AURA, analyses and
approvals, source editing/search, tool inventory, readiness, health,
observability, maintenance and settings. English/French interface selection
defaults to English and persists in browser storage; it changes UI text and
formatting without translating stored client content or changing voice language.
Locally served fonts/assets, responsive navigation, a keyboard command menu and
pausable/reduced motion apply throughout the interface.

Mission templates are editable intake drafts for the same SRE analysis path.
Selecting one does not submit work, discover client infrastructure, deploy an
agent fleet or create a tenant. Source and hypothesis review remain human tasks.
The control service queues bounded work for one serial analysis/maintenance
worker, persists status and exposes authenticated progress/decision routes.
Explicit human approval is still required before a diagnostic is delivered.

Opaque browser sessions, a one-use CLI login ticket, CSRF/origin checks, bounded
requests and private state protect the local operator workflow. They are not a
remote identity system or authorization between mutually untrusted clients.
The browser and CLI can perform explicitly supported operator mutations; the
control MCP has a separate read-only surface, with no approval or execution tool.

```mermaid
flowchart LR
  UI[Private EN / FR console] --> API[Loopback authenticated control API]
  CLI[Unified CLI] --> API
  CMCP[Control MCP: 9 read-only tools] --> API
  API --> State[Private console state]
  API --> Jobs[Serial analysis / maintenance worker]
  Jobs --> Graph[Supervised SRE graph]
  Graph --> RMCP[Runbooks MCP: 4 read-only tools]
  RMCP --> Corpus[Reviewed local corpus / Qdrant]
  API --> Ready[Bounded local readiness probes]
  API --> Aura[AURA local dialogue]
  API --> Voice[English / French CPU speech]
  Graph --> Gateway[Confidential local gateway aliases]
  Aura --> Gateway
```

## Readiness and local tools

`GET /api/preparation`, the Readiness page and `./plateforme preparation` /
`doctor` share one versioned response. Nineteen checks measure installed runtime
metadata, entrypoints, private storage permissions, Linux API socket bindings,
configured local destinations, live permitted aliases, six health endpoints,
source/index availability, voice artifacts and actual MCP handshakes. They run
independently under deadlines, share a short cache and return bounded evidence
without client content, credentials or raw exceptions. Suggested commands are
inert guidance, not automatic remediation.

The control MCP offers health, preparation, catalogue, analysis list/detail,
runbook list/read, search and bounded audit. It can only call fixed authenticated
GET routes on loopback, rejects redirects, bounds response bodies and never
initializes missing configuration. Its read-only annotations describe the
restricted implementation; they do not enforce a consumer's subsequent use of
returned confidential data. Connect only trusted local consumers.

Passing readiness means measured operational prerequisites, not certified
provider routing behind an alias, fresh semantic content, inference correctness,
microphone quality or production security approval. See [TOOLS.md](TOOLS.md) and
[ADR 0014](adr/0014-readiness-et-outils-locaux.md).

## AURA and speech lifecycle

AURA is a local AI conversation interface using the confidential gateway path.
It has no tools, approval authority or remediation path. Its ephemeral dialogue
is separate from persisted incident state. English is the default conversation
language; French is explicitly selectable independently of the UI language.

Piper synthesis and faster-whisper recognition run on CPU in a separate pinned
Python 3.13 environment; the API/agent/MCP runtime uses Python 3.14. Each selected
voice's artifacts are verified locally. No browser cloud recognition service is
used, and the application does not download models during voice requests.

Manual recording produces an editable transcript before submission. Explicit
hands-free mode sequences capture, local transcription, local dialogue, complete
WAV synthesis and playback, then reopens listening. Browser VAD ends a detected
spoken turn after roughly 1.6 seconds of silence; 12 seconds without speech or
20 turns ends the session. This is turn-taking, not simultaneous streaming.
Escape, tab hiding and route cleanup stop browser capture/playback and invalidate
pending continuations. Spoken input never grants an approval. Audio has bounded
size/duration and private temporary-file cleanup; model weights are reinstallable
and excluded from platform backups. See [VOICE.md](VOICE.md) and
[ADR 0013](adr/0013-voix-anglaise-reactive.md).

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

Use separately qualified deployments/VMs for separate clients; a title, mission
preset or alternative state directory does not isolate the shared gateway,
corpus, index and backups. [CLIENT-WORKFLOW.md](CLIENT-WORKFLOW.md) makes that
boundary explicit. The [26 September 2026 security assessment](SECURITY-RELEASE-2026-09-26.md)
retains 166 HIGH package occurrences and grants only conditional continued use
in the existing supervised local scope. Unqualified production security approval
and remote/mutually untrusted use remain NO-GO at that snapshot.
