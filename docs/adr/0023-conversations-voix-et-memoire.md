# 0023 — Local conversations, natural speech and explicit graph context

Date: 2026-09-27. Status: implementation qualified for the local private scope.

## Context

The operator needs persistent bilingual dialogue, document interpretation and reusable
engineering context. The existing temporary AURA endpoint deliberately has no tools
or action authority. The operator now requests the name **Védric** in both languages,
French **vous**, and operating-system default audio devices.

## Decision

- Keep the confidential `local` alias and the existing inference lock. Stream bounded
  text to the browser, commit complete user/assistant pairs atomically, and reject
  an idempotency key reused with a different message, language or source selection.
- Store conversations in the existing private SQLite database. Retain inactive
  conversations for 30 days, at most 500 conversations and 200 turns per conversation,
  with a 96 MiB content budget. Send at most seven recent messages and bounded
  selected attachments as context; this is not unlimited recall.
- Parse documents in a disposable subprocess with resource limits, a deadline,
  hardened XML, archive limits and network/child-process denial. These measures are
  **not an OS security sandbox**. No macros or formulas execute; scanned PDFs require
  page images. Normalized images lose metadata and retain at most 1600 pixels per side.
- Preserve paragraph punctuation for speech and add only missing silence between
  synthesized sentences. Do not simulate human breathing, hide the AI identity or
  claim a new trained model. French/English female voice weights remain pinned.
- Use a dedicated authenticated Neo4j instance for explicit operator notes and
  same-scope links. Customer databases already present on the machine are not reused.
  NEXUS exposes two read-only memory tools through its control namespace. ATLAS's
  four-tool runbook profile keeps its existing authority.
- Copy a memory note into an AURA conversation only after the operator selects it.
  The copy is an untrusted attachment with its source and timestamp; it does not
  become a verified runbook or an approval. Graph notes and conversation copies have
  independent deletion/backup lifecycles.
- Include the dedicated graph's bounded logical notes/relationships in platform
  backups. Refuse malformed/cross-scope relationships and verify complete content
  in a disposable authenticated Neo4j instance. Do not imply atomicity across the
  platform's independent databases; quiesce writes for continuity backups.

## Alternatives rejected

An external speech service would change the confidentiality boundary. Automatic
cross-conversation or cross-client retrieval would blur provenance and scope. Granting
arbitrary Cypher or generic command tools would expand authority beyond the task.

## Consequences

Private state now contains conversation text, extracted documents and selected graph
notes. Disk encryption, backups and client-specific installations remain operator
responsibilities. Scope filters are an application feature, not multi-tenant isolation.
Local voice quality and microphone latency remain hardware/browser dependent.
Qualification results belong to the release report; this ADR does not certify them.

References: [OWASP file upload guidance](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html),
[Neo4j Docker operations](https://neo4j.com/docs/operations-manual/current/docker/introduction/),
[pypdf extraction limitations](https://github.com/py-pdf/pypdf/blob/main/docs/user/extract-text.md).
