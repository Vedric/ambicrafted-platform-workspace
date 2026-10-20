# ADR 0040 — Typed local conversation artifacts

Date: 2026-10-20

Status: Accepted for implementation; real model and browser qualification are separate evidence.

## Context

AURA previously returned short plain text, including when the operator requested
an architecture diagram or a report. Prose describing a diagram is not a usable
diagram. Generated HTML, SVG or executable diagram languages would introduce
unnecessary rendering authority. A useful artifact also needs persistence,
exports, explicit source boundaries and compatibility with existing conversation
history, rather than a transient image displayed once.

## Decision

Extend the authenticated conversation turn with `format: auto | text | diagram |
report`, defaulting to `auto`. Auto selects a structured reply only for a bounded
set of explicit English/French creation intents. Ordinary conversation retains
its existing streaming path and token budget. Operators can select a format
explicitly; ambiguous requests remain text. This avoids an additional model
classification call on every turn.

Generate a single typed JSON document through the fixed local gateway, the
`local` alias and the restricted confidential key. Use JSON Schema constraints
and then validate the completed response in the API. A missing key, timeout,
non-normal finish, invalid schema, unknown source, inconsistent graph or size
limit produces a visible error; no partial document or turn is saved. There is
no template fallback presented as a successful model generation.

A second local call can reject the unchanged proposal before persistence.
Code-owned references cover every textual unit and table row; exact unique
coverage is mandatory. The reviewer distinguishes supplied context, proposals
and unknowns, and checks contradictions, unsupported claims and edge direction.
It cannot rewrite or certify the document. There are at most two calls, 6,000
output tokens per call, a shared 180-second deadline and a 90-second review
ceiling. Review refuses documents exceeding 128 units or a 128-KiB catalog;
it never silently truncates the review. Actual reported usage is aggregated.
This additional fallible check was introduced after real synthetic reports
incorrectly changed an unspecified restore test into an absent/untested one.

Diagram documents contain bounded nodes, edges, flat groups and a legend.
Reports contain bounded sections, paragraphs, bullets and rectangular tables.
The API accepts no arbitrary layout coordinates, CSS, HTML, SVG, external URL
fields or executable diagram source. The frontend owns layout and export
rendering from these semantic values. The full artifact is limited to 64 KiB,
one per turn and twenty per conversation. NDJSON clients allow a 128 KiB frame
to accommodate the artifact plus the final reply envelope, with the existing
1 MB total stream bound retained.

The API builds a source catalog from the exact bounded context sent to the
model, with hashes and truncation information. Previous assistant messages and
the most recent same-conversation artifact are `generated` context. A reference
to generated material cannot alone support `basis=provided`. All sources remain
`verified: false`: source existence and byte identity do not establish factual
truth, entailment or source relevance. Proposed designs and unknown information
are distinguished in the document and presentation. Professional prose belongs
inside the document; draft/provenance labels belong in the surrounding interface
and exports, without repetitive disclaimers in every section.

Persist artifact JSON in `artefacts_conversation` in the same SQLite transaction
as the user/assistant pair and operation fingerprint. Parent integrity uses the application transaction and restore checks, not new SQL foreign keys. Reusing an operation ID
returns the saved artifact; changing its request or explicit format conflicts.
Existing payload fingerprints are preserved for omitted/default auto format.
Old messages expose an empty artifact list. No destructive schema migration is
needed. Quotas, conversation deletion and 30-day retention include artifacts.
The authenticated export endpoint returns portable JSON or escaped Markdown;
the frontend may additionally render SVG, PNG and print/PDF locally.

SQLite snapshots already copy the new table. Backup inventory and restore drills
now additionally check its row count, conversation parent and assistant-message
parent. Historical snapshots without the table remain accepted. A manifest that
declares artifacts but loses the table or its records is rejected.

There is no automatic Neo4j write. Saving information to memory goes through a
visible, editable draft and the existing explicit note form, with a selected
scope, source and operator confirmation. The default draft is a question, not a
verified fact. This does not grant an artifact execution or approval authority.

## Alternatives rejected

- Model-authored HTML/SVG or unrestricted diagram code: unnecessary executable
  rendering surface and uncertain portable export semantics.
- Automatically saving every model inference into Neo4j: turns assumptions into
  durable context without deliberate operator review.
- Returning a stock diagram when generation fails: creates false success.
- Running another classifier model for ordinary turns: adds latency and token
  cost without improving the explicit format control.
- Introducing a separate object store or graph schema for every document:
  unnecessary for the bounded single-operator platform; SQLite backup and
  retention already provide the required lifecycle.

## Consequences

Structured generation takes longer than a short spoken response. The interface
must show that generation is in progress and keep the previous saved history
available after failure. Source validation does not replace technical review of
the generated architecture or report. Real local-model output and browser
layout/export need their own qualification; passing schema and unit tests alone
does not prove document quality. Scope remains one local operator, not tenant
authorization for a hosted commercial service.

Schema implementation uses the installed Pydantic v2 validation API, checked
against its [JSON Schema documentation](https://docs.pydantic.dev/latest/concepts/json_schema/)
and [model validator documentation](https://docs.pydantic.dev/latest/concepts/validators/).
