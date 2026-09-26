# Runbooks MCP and indexer

Four read-only tools are published over stdio: `list_runbooks`, `read_runbook`,
`search_runbooks`, and `semantic_search`. Start from the checkout root when
using `.mcp.json`; its paths are relative to that root.

```sh
uv sync --locked --project mcp-servers/runbooks
uv run --locked --directory mcp-servers/runbooks server.py
uv run --locked --directory mcp-servers/runbooks indexer.py --dry-run
uv run --locked --directory mcp-servers/runbooks indexer.py
```

The indexer and semantic tool use `CONFIDENTIAL_KEY` and `local-embed` through
the gateway. Configure `RUNBOOK_DIR`, `LITELLM_BASE_URL`, `QDRANT_URL` and
`QDRANT_COLLECTION` when their defaults do not apply. The agent forwards these
values explicitly to its MCP subprocess.

## File and tool contracts

All reads go through `fichiers.py`: flat Markdown names only, no symlinks,
regular files only, and a bounded read. Opening uses a directory descriptor
and `O_NOFOLLOW`, including for inventory, literal search and indexing.
Invalid files do not contribute content to inventory/search/indexing.

`read_runbook` returns JSON text with `fichier`, `texte`, `sha256`, and
`tronque`. Its content limit is 8,000 characters; an agent must not accept a
truncated envelope as complete provenance. Errors are explicit text, never
successful read envelopes. Large documents should be split into focused runbooks.

`search_runbooks` searches **literal text**, case-insensitively. Regular
expressions are deliberately unsupported. Context is 0..10 lines, the query
is at most 2,000 characters, and results are bounded.

Semantic search returns up to 20 fragments and uses a 0.60 minimum cosine
score. It can abstain and refuses a stale corpus fingerprint. These controls
do not establish semantic correctness; benchmark the threshold when changing
the model or corpus. Failed semantic search directs the caller to literal search.

## Safe indexing and migration

The indexer validates every vector and index, builds a fresh physical
collection, verifies the point count, and atomically updates the
`runbooks-current` alias. It never deletes the previous index before writing.
Old versions are retained for rollback; a failed switch may require inspecting
the current alias before cleaning a staging collection.

An old physical `runbooks` collection remains intact. Use the new alias name;
setting `QDRANT_COLLECTION` to a pre-existing physical collection is refused.
Never replace this refusal with a delete-and-create migration.

Markdown sections remain intact. Oversized sections are refused before
indexing and should be split at meaningful headings. Point identifiers are
deterministic; corpus changes produce a new fingerprint. Reindex after every
runbook change before trusting semantic results.

To roll back, atomically point the alias to the retained version. Clean only
physical versions confirmed unused by **all** aliases, after verifying the
active index and retaining the rollback version. The host's other projects
and collections are outside this maintenance scope.

## Tests

```sh
cd mcp-servers/runbooks
uv run --locked pytest -q
uv run --locked ruff check .
```

Tests cover normal reads, traversal and symlink rejection, non-regular files,
regex-shaped literal input, malformed embeddings, stale results and failures
before index publication. Qdrant and the gateway are simulated in this suite.
