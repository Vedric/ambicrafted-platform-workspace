# AURA diagrams and reports

AURA can produce a saved architecture diagram or a structured report inside a
conversation. Generation uses the local gateway and confidential key. A
generated document is a draft to review, not proof that the described system was
inspected, deployed or tested.

## Request a document

Use an explicit instruction such as:

- `Create a diagram showing a browser calling an API that queries PostgreSQL.`
- `Crée un schéma de cette architecture : navigateur, API, PostgreSQL.`
- `Create a report separating the supplied observations, hypotheses and next checks.`
- `Rédige un rapport de cet incident, sans inventer de métriques manquantes.`

The automatic mode recognizes explicit leading creation requests in English and
French. Questions about diagrams, quoted instructions, negations and ambiguous
requests stay in normal conversation. Choose **Diagram** or **Report** explicitly
when the wording does not match. Auto detection is deterministic and bounded;
it is not a general-purpose intent classifier.

Attach the relevant private source documents to the same conversation and select
them for the turn. Only the supplied recent conversation, selected attachments
and most recent same-conversation artifact are available. A previous generated
artifact is marked generated context; it does not become verified evidence.
Source hashes identify the bounded excerpts sent to the model. A clipping flag
means some source material was omitted, and source presence does not prove that
the generated statement is supported by it.

## Save, export and memory

The final document and its user/assistant messages are saved atomically. Closing
the page during an unfinished response does not produce a successful partial
artifact. If a request fails, the interface shows an error. Reuse the same
operation ID when checking or retrying an uncertain request to avoid duplication.

JSON is the portable semantic document, including sources, component identities,
groups and relationships. Markdown is an escaped text representation suitable
for review and version control. Visual SVG/PNG/print exports are produced by the
frontend renderer; they do not contain model-authored SVG or HTML. SVG and PNG preserve the diagram; print/PDF uses the complete text outline or report, rather than shrinking a large graph onto one page.

Memory is separate. Review the generated material, open the explicit memory
draft, select the correct scope, edit the note and save it deliberately. The
default question type prevents an unreviewed suggestion from being presented as
a confirmed fact. Nothing is automatically ingested into Neo4j after generation.

## CLI

The CLI uses the same generation, authorization and persistence path. Supply
private content through a file owned by the operator with permissions `0600`, or
through stdin. Do not put confidential material in shell arguments.

```sh
./plateforme conversations creer
./plateforme conversations dire CONVERSATION_UUID --format diagram --langue fr \
  --fichier /path/to/private-request.txt --operation-id OPERATION_UUID
./plateforme conversations voir CONVERSATION_UUID
./plateforme conversations exporter CONVERSATION_UUID --artefact ARTIFACT_UUID \
  --format markdown --sortie /path/to/new-private-report.md
```

`CONVERSATION_UUID` is returned by `creer`; use a real UUID for `OPERATION_UUID`
and keep it for retries. The default format is `auto`; accepted explicit values
are `text`, `diagram`, and `report`. The result includes the same artifact JSON as
the UI. `exporter` accepts `json` or `markdown`, validates the scoped artifact and creates a new mode-0600 file without overwriting an existing path. HTTP errors, wrong identity/type, an oversized or incomplete response create no file. SVG/PNG rendering remains a UI feature. Save terminal output only to an appropriately private destination.

## API contract

`POST /api/conversations/{conversation_id}/messages` retains its existing request
fields and adds optional `format`. The final NDJSON event includes
`artefacts: [ArtifactV1]` for a structured reply. No partial diagram is emitted.
Saved `messages[]` include `id` (integer), `operation_id` and `artefacts` (empty for
historical/plain-text messages).

`GET /api/conversations/{conversation_id}/artefacts/{artifact_id}/export?format=json`
downloads the authenticated JSON document. Use `format=markdown` for the text
export. Both identifiers are scoped together: an artifact from another
conversation is not returned. Responses inherit the API's no-store policy and
download disposition.

Artifact fields are `id`, `schema_version: 1`, `type: diagram | report`, `title`,
`summary`, `sources`, and `document`. Source fields are `id`, `label`, `kind`,
`sha256`, `truncated`, and `verified: false`. Source kinds are `request`, `history`
(operator message), `attachment`, and `generated` (previous model output).

| Document | Structure and limits |
| --- | --- |
| Diagram | `direction`: `LR` or `TB`; 1–24 `nodes`, 0–40 `edges`, 0–6 flat `groups`, 0–8 `legend` entries |
| Node | `id`, `label` (100 characters), `description` (240), `kind` (`service`, `data`, `actor`, `external` or `control`), nullable `group_id`, `basis`, `source_ids` |
| Edge | `id`, `source`, `target`, `label` (100), `kind` (`flow`, `dependency` or `trust`), `basis`, `source_ids`; known distinct endpoints only |
| Group | `id`, `label` (100), `description` (300); no nested groups |
| Legend | `kind` from the node/edge kinds; `label` (160), unique kind |
| Report | 1–10 `sections` |
| Section | `id`, `heading` (160), 0–6 `paragraphs` (1,800 each), 0–12 `bullets` (600 each), nullable `table`, `basis`, `source_ids`; must contain material |
| Table | 1–8 `columns` (100 each), 0–30 `rows`, rectangular; cells at most 500 characters |

IDs use `[a-z][a-z0-9_-]{0,47}` and diagram IDs are unique across nodes, edges and
groups. `basis` is `provided`, `proposed`, or `unknown`; `provided` requires at
least one known nongenerated source. There are at most 20 sources, 16 source
references per item, 160 characters per source label, 160 per title and 1,200 per
summary. Unknown fields, raw HTML/SVG, URL payloads, invisible controls and code
fences are rejected. The complete artifact is at most 64 KiB, with at most one
artifact per turn and twenty per conversation.

## Bounded local consistency review

After schema validation, a second local inference reviews the original bounded
sources against the proposed document. Code assigns separate references to the
title, summary, diagram components/edges/groups/legend, report headings,
paragraphs, bullets, table headers and every table row. The response must cover
every reference exactly once. The reviewer can reject an unsupported statement,
contradiction, incorrect direction or change from unknown to absent. It cannot
rewrite the document, add facts, or label it verified. A positive review only
means that this fallible model found no blocking discrepancy; human review
remains necessary, and false acceptances or unnecessary refusals are possible.

The two calls share a 180-second deadline; review also has its own 90-second
ceiling. Each call allows at most 6,000 output tokens (12,000 combined), with no
automatic retry or repair call. Reported usage is added; missing usage remains
unknown. The review catalog is limited to 128 units and 128 KiB; larger documents
fail visibly instead of receiving a partial review. Existing source-context
bounds still apply. Failure, incomplete coverage, cancellation or a rejecting
verdict publishes no artifact and saves no partial conversation pair.

Failed document streams retain the existing public error message and add a
finite `code`: `document_output_invalid`, `document_review_invalid`,
`document_review_rejected`, `document_timeout`, `document_upstream`,
`document_storage` or `document_unknown`. These identify the observed failure
boundary, not an inferred root cause or a claim that a rejected statement is
wrong. The API emits a warning JSON record containing only `category` and the
validated `operation_id`. No source, model output, exception text, traceback or
credential is recorded. Cancellation propagates without being relabelled as a
document failure. There is no new retry, repair, metric or stored draft.
See [operational diagnosis](OPERATIONS.md#document-generation-diagnostics) and
[ADR 0046](adr/0046-diagnostic-erreurs-documents.md).

## Lifecycle and recovery

Artifacts count toward the existing 96 MiB conversation storage quota. Deleting
or expiring a conversation deletes its artifacts. Retention is 30 days of
conversation inactivity; exporting an artifact does not extend it. SQLite
backups include artifacts and restore drills verify their counts and parents. Parent consistency is enforced by application transactions and restore checks, not newly introduced SQL foreign keys.
Keep the existing backup/export procedures for confidential content; a browser
download is not an off-host recovery policy.

Historical databases acquire an empty artifact table without rewriting old
messages. Old backups without artifacts remain valid. Restore refuses a new
manifest that loses its declared artifact records or restores orphan artifacts.
