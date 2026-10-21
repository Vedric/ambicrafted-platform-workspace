# ADR 0046 — Safe document failure diagnostics

Date: 2026-10-21. Status: accepted.

## Context

Two real synthetic document attempts were not published after promotion. The stream
collapsed transport, output validation, review rejection and persistence errors
into one public message. Their causes cannot be established retrospectively.
Re-generating is stochastic and consumes another local inference; it is not a
diagnostic of an earlier response.

## Decision

Add seven finite document error codes. Code-owned validation scopes distinguish
invalid generation output from invalid/incomplete review. A complete validated
review with a non-retain verdict gets its own rejection code. Typed transport
and timeout exceptions retain those categories across both calls. Failures
inside turn persistence are classified as storage, including validation errors
there; they are never relabelled as malformed model output. Other caught failures
remain unknown. No category is extracted from arbitrary exception prose.

Document NDJSON errors add `code` while preserving the public message. One
structured warning contains only category and the validated operation identifier.
It includes no payload, exception text, traceback, credentials or model-authored
reason. No metric labels or persistent business records are added. Cancellation
still propagates. Generation/review prompts, budgets, schemas, acceptance rules,
call count and persistence transaction are unchanged.

## Alternatives rejected

- Logging complete model exchanges or raw exceptions would expose confidential
  source material during routine operation.
- Guessing a category from exception text would confuse output and storage
  failures and allow untrusted wording to determine operational claims.
- Automatic regeneration, permissive review or publishing rejected drafts would
  change quality and publication policy instead of fixing observability.

## Consequences

The journal can correlate an operation with a failure boundary without another
model call. It intentionally cannot reconstruct the discarded draft or explain
every semantic verdict. The operation identifier adds a small private log record
per caught document failure; existing service-journal retention applies.

Tests exercise real validators and transactions against a substituted HTTP
boundary, including malformed envelopes, all rejecting verdicts, incomplete
coverage, transport/deadline failures, SQLite rollback, cancellation and sensitive
exception/body material. They check exact response/log fields and no extra call.
Local qualification and review are recorded separately from hosted CI.

A new diagnostic report was accepted despite overstating uncaptured logs as
unavailable. This change neither fixes that semantic failure nor qualifies model
expertise. The two original non-publication causes remain unknown.
