# ADR 0002: semantic search over the runbooks (Qdrant + MCP)

Status: accepted, in local service since 2026-08-25
Date: 2026-08-25

## Context
The runbooks MCP server only offered regular-expression search, line by line.
It is unbeatable on an exact term (error code, service name) but goes silent
as soon as the question rephrases: during an incident, you type what you
observe ("the service keeps restarting"), not the runbook's vocabulary
("crash-loop"). An operator under pressure does not guess the keyword.

## Decision

### Storage
Qdrant added to the gateway stack, image pinned to `qdrant/qdrant:v1.19.0`,
port 6333 published on 127.0.0.1 only, named volume `qdrantdata`. Collection
`runbooks`, 768 dimensions, cosine distance.

### Chunking: by markdown section, never by character count
This is the structuring decision. Fixed-size chunking cuts in the middle of a
numbered procedure and returns "2. daemon-reload, reset-failed, restart"
without step 1. During an incident, a fragment of a procedure is more
dangerous than no result at all: it looks complete. Chunking therefore
follows the heading hierarchy, one section per fragment. Headings located
inside a fenced code block are ignored (a shell comment is not a heading).

### Heading-path prefix
Each fragment carries its full path, for example
`# Service systemd en crash-loop > ## Diagnostic`. This is the most profitable
gain in the pipeline: without it, a "## Diagnostic" fragment is
indistinguishable between the systemd runbook and the PostgreSQL runbook,
both at embedding time and at retrieval time.

### Embeddings
Exclusively through the gateway (`/v1/embeddings`, alias `local-embed`),
never directly to Ollama: otherwise the routing, the tracking and the
compartmentalisation of ADR 0001 are bypassed. The key used is
`CONFIDENTIAL_KEY` (virtual key `confidential-only`), not the master key:
least privilege, and consistency with rule 2.
The task prefixes of nomic-embed-text are applied
(`search_document:` when indexing, `search_query:` when querying): the model
is trained for asymmetric search, and omitting them degrades recall on
rephrasing.

### Idempotence
The collection is recreated on every run, and point identifiers are
deterministic (UUIDv5 over `fichier:ligne:chemin_titres`). Recreation
eliminates orphan fragments from a deleted or renamed section, which plain
upserts would leave in place; stable identifiers make two runs comparable.

### Exposure
`semantic_search(requete, k)` added **alongside** `search_runbooks`, which is
kept as it is. The two are complementary and the tool description says so
explicitly to the model. The regression would be to replace an exact tool
with an approximate one.

### Degradation
If Qdrant, the gateway or the dependency is missing, `semantic_search`
returns a message that names the cause, gives the fixing command and points
back to `search_runbooks`. It never raises: an unavailable RAG brick must not
take down the three tools that depend only on the file system.

## Alternatives rejected
- **pgvector on the existing Postgres**: avoids one more service, but that
  Postgres holds the gateway's spend accounting. Mixing an application index
  into it couples two unrelated life cycles (a reindex must not be able to
  disturb billing).
- **Fixed-size chunking with overlap**: simple, and wrong here. See above.
- **In-memory index inside the MCP server**: reindexing on every start, no
  possible inspection of the state.
- **Direct call to Ollama**: bypasses ADR 0001.
- **Replacing `search_runbooks`**: would lose exact search, the only reliable
  one on an error code.

## Consequences
+ Value demonstrated by test on 08-25: `search_runbooks("redémarre en
  boucle")` finds nothing (the expression is absent from the corpus), whereas
  `semantic_search("le service redémarre en boucle")` ranks the four
  fragments of the crash-loop runbook at positions 1 to 4, ahead of the
  PostgreSQL runbook.
+ Degradation verified: with Qdrant stopped, the tool returns an actionable
  message and `search_runbooks` keeps answering.
+ Idempotence verified: two consecutive runs, 7 points, identical
  identifiers.
- The index is not refreshed automatically: run `uv run indexer.py` after any
  runbook change. A hook remains to be decided.
- The window of nomic-embed-text is 2048 tokens. The current corpus is far
  below it (longest fragment: 295 characters), but the indexer warns beyond
  6,000 characters because Ollama truncates silently.
- One more service to operate.
