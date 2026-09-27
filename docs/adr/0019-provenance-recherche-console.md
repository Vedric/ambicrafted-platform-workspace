# 0019 — Reject stale semantic results at the console boundary

Date: 2026-09-27. Status: accepted.

## Context

The runbook MCP already rejects results whose corpus fingerprint differs from the
current source files and requests a minimum relevance score. The console's direct
REST search previously validated payload types but did not check that provenance.
Editing a runbook could therefore leave an older indexed passage visible in the
UI. The supervised agent still reread source files and enforced its own citation
checks; that separate protection did not make the UI result current.

## Decision

The control API must verify semantic results against a bounded snapshot of the
current local Markdown corpus, using the indexer's canonical segmentation and
fingerprint contract. It checks freshness across the asynchronous query, validates
source identity and passage content, and applies the same minimum score of 0.60.
Missing or inconsistent provenance fails closed through the existing sanitized
503 response. Literal search remains available. Reindexing stays an explicit
maintenance operation; a failed query does not mutate source files or the index.

A contract test compares the API snapshot with the real indexer on representative
Markdown structures. Regression tests cover stale or altered fragments and source
changes during a query, in addition to the existing HTTP/schema/privacy bounds.
Potentially expensive filesystem work must not block the asynchronous server loop.
The API imposes additional memory budgets: at most 8,000,000 source bytes across
the corpus, 8,000,000 expanded fragment characters and 10,000 fragments, alongside
the indexer's 1,000 directory-entry and 200,000-byte per-file bounds. Expanded
heading paths count before concatenation. Exceeding a budget produces the same
sanitized refusal; no partial result or truncated fingerprint is accepted.
Search requests are serialized within the existing timeout. A separate nonblocking
thread lock prevents concurrent snapshots if cancellation leaves a worker running.
Cancellation cannot terminate a filesystem call already in progress; new snapshots
are refused until that worker exits, rather than accumulating blocked reader threads.

## Alternatives rejected

- Relying on the agent's later checks: console users can inspect search results
  independently of an agent, so freshness belongs at this boundary too.
- Returning stale results with an implicit warning: the existing result contract
  has no trustworthy stale-result mode; a clear unavailable state is less ambiguous.
- Automatically rebuilding on a search request: this changes durable state from
  a read endpoint and hides the reviewed-source publication decision.
- Lowering citation requirements to improve a model demonstration: provenance
  rules are independent of the model's ability to format its proposed actions.

## Consequences

Search gains bounded filesystem reads and hashing, and an edited/unpublished
corpus can temporarily make semantic search unavailable. Operators explicitly
reindex reviewed changes or use literal search. The shared contract test guards
against segmentation drift between separately installed projects. This verifies
source freshness and exact passage provenance, not factual correctness, diagnostic
quality or production approval. Client acceptance and the image findings remain
separate release conditions.
