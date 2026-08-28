# MCP server: runbooks

Read-only access to the runbook corpus, exposed over MCP. Four tools, one
resource, one prompt. Nothing here writes anything, anywhere — which is what
makes it usable by an agent that must not be able to change production.

This server is the agent's **only** tool provider. Its read-only nature is
therefore not a convenience, it is guardrail 3 of the platform (see
[`SECURITY.md`](../../SECURITY.md)).

## Tools

| Tool | Signature | What it is good at |
|---|---|---|
| `list_runbooks` | `() -> str` | inventory: file name, size, title |
| `read_runbook` | `(nom: str) -> str` | one complete runbook, by file name only |
| `search_runbooks` | `(terme: str, contexte: int = 2) -> str` | **exact** search: error code, service name, command. Regex, case-insensitive, with surrounding lines |
| `semantic_search` | `(requete: str, k: int = 5) -> str` | **rephrased** search: "the service keeps restarting" finds "crash-loop" |

`search_runbooks` and `semantic_search` are complementary and neither
replaces the other. The tool description says so explicitly to the model, and
tells it to call both when in doubt. Replacing the exact tool with the
approximate one would have been the regression (ADR 0002): on an error code,
regex is the only reliable one.

Also exposed:

- **Resource** `runbook://index` — the inventory, injectable as context.
- **Prompt** `diagnostic(symptome)` — a guided diagnostic template that ends
  with "propose no remediation without citing the runbook that grounds it, or
  saying clearly that it is undocumented".

## Guardrails inside the server

**Every file access is confined to `RUNBOOK_DIR`.** `_resoudre()` refuses any
name containing a separator or starting with a dot, then resolves the path
and re-checks containment with `is_relative_to`. Two checks rather than one,
because the first is about the shape of the input and the second about the
result of resolution.

**A name coming back from Qdrant is re-validated.** The `fichier` field of a
search payload comes from outside the process, and the model will very likely
pass it straight to `read_runbook`. It goes through `_resoudre()` before
being offered; if it fails, it is displayed marked as invalid rather than
silently dropped.

**Everything returned is bounded**, so that an abnormally large runbook
cannot push the instructions out of the model's context:

| Limit | Value | Applies to |
|---|---|---|
| `MAX_RESULTATS` | 50 | regex matches per `search_runbooks` |
| `MAX_TAILLE` | 200,000 chars | one runbook, and the total of a semantic response |
| `MAX_K` | 20 | fragments per `semantic_search` |
| `MAX_EXTRAIT` | 4,000 chars | a single returned fragment |

The agent adds its own cap on top: `MAX_RESULTAT_OUTIL = 12,000` characters
per tool result.

**A refusal is a message, never an exception.** Out-of-scope path, invalid
regex, missing file, unavailable RAG: the tool returns a text the model can
read and act on. An exception would abort the loop; a message lets the agent
correct course and stay auditable.

## Degradation

The RAG import is **guarded**. `list_runbooks`, `read_runbook` and
`search_runbooks` depend only on the file system and must keep working when
the vector stack is absent or broken — a missing dependency must never stop
the server from starting.

When `semantic_search` cannot work, it names the cause, gives the fixing
command, and points back to `search_runbooks`:

| Cause | Message says |
|---|---|
| dependency missing | `cd mcp-servers/runbooks && uv sync` |
| collection absent | `uv run indexer.py` |
| Qdrant unreachable | `docker compose up -d qdrant` |
| embedding failed | the exception, plus the fallback |

Verified with Qdrant stopped: the tool returns an actionable message and the
three other tools keep answering (ADR 0002).

## The indexer

`indexer.py` builds the Qdrant collection from `runbooks/*.md`.

```sh
uv run --directory mcp-servers/runbooks indexer.py --dry-run   # split only, no network
uv run --directory mcp-servers/runbooks indexer.py             # embed and write
```

**Chunking is by markdown section, never by character count.** This is the
structuring decision, not an implementation detail. A fixed-size split cuts
through a numbered procedure and returns step 2 without step 1 — and during
an incident, a fragment of a procedure is more dangerous than no result,
because it looks complete. Headings inside fenced code blocks are ignored: a
shell comment is not a heading.

**Each fragment carries its full heading path**, e.g.
`# Service systemd en crash-loop > ## Diagnostic`, and that path is part of
the embedded text. It is the cheapest large win in the pipeline: without it,
a `## Diagnostic` fragment is indistinguishable between two runbooks, both
when embedding and when displaying.

**Asymmetric task prefixes.** nomic-embed-text is trained for asymmetric
search: `search_document: ` when indexing, `search_query: ` when querying.
Omitting them measurably degrades recall on rephrasing.

**Embeddings go through the gateway, never straight to Ollama** — alias
`local-embed`, key `CONFIDENTIAL_KEY`, not the master key. A direct call
would bypass the routing, the spend tracking and the compartmentalisation of
ADR 0001. The consequence that matters: **the search query does not leave the
machine either.**

**Idempotent.** The collection is recreated on every run and point ids are
deterministic (UUIDv5 over `fichier:ligne:chemin_titres`). Recreation removes
orphan fragments left by a deleted or renamed section, which plain upserts
would keep; stable ids make two runs comparable.

**Two checks that fail loudly.** The embedding dimension must be 768 — if it
is not, the `local-embed` alias no longer points at nomic-embed-text, and the
run stops rather than building a subtly worse index. And any fragment over
6,000 characters is flagged, because nomic-embed-text's window is 2,048
tokens and Ollama truncates silently past it.

Current corpus: 2 runbooks → 7 fragments, longest 295 characters.

## Configuration

| Variable | Default | Role |
|---|---|---|
| `RUNBOOK_DIR` | `<repo>/runbooks` | corpus directory; every access is confined to it |
| `LITELLM_BASE_URL` | `http://localhost:4000/v1` | the gateway |
| `CONFIDENTIAL_KEY` | — | virtual key restricted to `local` / `local-embed` |
| `QDRANT_URL` | `http://127.0.0.1:6333` | vector store |
| `QDRANT_COLLECTION` | `runbooks` | collection name |

The repository root is derived from the file's own location, so the defaults
work without any environment at all for the three file-system tools.

## Running it

The agent starts this server itself, as a stdio subprocess, and passes it the
environment it needs (`outils.py`). You rarely need to start it by hand.

```sh
# Manually, for debugging
uv run --directory mcp-servers/runbooks server.py

# From the agent, with the server's stderr visible
SRE_DEBUG_MCP=1 uv run sre-agent "..."
```

By default the agent redirects the server's stderr to `/dev/null`: the MCP
SDK logs in clear on that stream and, during an incident, it drowns the
agent's own output.

It is also registered in `.mcp.json` at the repository root, so Claude Code
can use the same four tools directly.

**Note the entry point.** `[project.scripts]` declares `runbooks-mcp`, but
that still points at the generator's scaffolding — running it prints
`Hello from runbooks-mcp!` and starts nothing. The server is `server.py`.
The scaffolding in `src/runbooks_mcp/__init__.py` and the placeholder
`description` in `pyproject.toml` are leftovers worth cleaning up; they are
recorded here rather than left to surprise someone.

## Dependencies

`mcp[cli]>=2,<3` (SDK 2.0.0 locked), `httpx>=0.28,<0.29`,
`qdrant-client>=1.19,<2`. Bounded floor-and-ceiling, per rule 7.
