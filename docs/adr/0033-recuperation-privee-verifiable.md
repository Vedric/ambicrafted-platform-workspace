# 0033 — Verified private backup inventory and encrypted recovery staging

Date: 2026-10-20. Status: implemented for the private single-operator scope.

## Context

The previous backup preserved databases but omitted the active Markdown corpus
and separate mission files. A successful empty-state drill could not establish
that an operator's conversation, attachment, graph context and checkpoint were
recoverable. A local plaintext backup also does not survive loss of the host.

## Decision

- Extend the existing backup-v1 manifest compatibly with file sizes/SHA-256,
  repository revision/dirty state, explicit source mappings and exclusions.
  Verify the full inventory before any disposable restore. Legacy backups remain
  readable with an explicit missing-integrity result, never silently upgraded.
- Include the active top-level corpus and explicitly configured extra mission
  roots. Refuse links, special files, unsafe permissions, source/destination
  overlap and exceeded file/byte limits. Never automatically back up the home
  directory, and never include browser sessions or login tickets.
- Preserve individual database consistency; do not pretend it is a distributed
  snapshot. Require quiescent writers for continuity backups before upgrades.
- Use the existing qualified **age v1.3.1 CLI**, standard public recipients and
  a standard USTAR archive, rather than implementing cryptography or adding a
  storage-provider SDK. Encryption and identity files are never logged. Off-host
  destination, retention and private-key custody are explicit operator choices.
- Authenticate the entire encrypted payload before bounded extraction. Reject
  special members, traversal, duplicate paths, extended metadata and overwrites.
  Publish only a newly created private staging directory after verification;
  never replace active application state automatically.
- Hash the bytes actually consumed by the archive writer against the frozen
  inventory, and serialize the already validated manifest. Before/after source
  checks alone cannot detect a concurrent change reverted during the copy.
- Support optional encrypted staging after the scheduled backup. Fail the job
  if a configured export fails while preserving its completed local snapshot.
  A writable output directory is not evidence of an off-host copy or valid mount.
- Exercise nonempty production state without model calls: report, real LangGraph
  checkpoint, conversation, extracted attachment, two notes/one relationship and
  authentication exclusion. Restore Neo4j only in an explicitly requested
  disposable container. Keep real-service backup drills and model-quality tests
  separate from this synthetic recovery test.

## Alternatives and consequences

Restic is a strong option for an eventual selected storage backend, but choosing
credentials, a remote account or a retention policy without that context would
not prove disaster recovery. The age export is transport-independent and uses
an already installed tool. A future restic integration can back up the encrypted
exports or replace this transport after qualification.

No encryption key or remote storage is silently provisioned. RPO/RTO and recovery
on a second machine remain measurable acceptance criteria. Plain temporary data
requires encrypted workstation storage; normal deletion is not secure SSD
erasure. USTAR naming and bounded inventory limits are explicit and fail closed.
PostgreSQL roles/grants, historical monitoring volumes and model caches retain
separate recovery requirements, documented in [Recovery](../RECOVERY.md).

Sources checked through Context7: [official age CLI](https://github.com/FiloSottile/age/blob/main/README.md),
[LangGraph persisted state](https://docs.langchain.com/oss/python/langgraph/checkpointers).

The pinned private age installer and service PATH are documented in
[Host tools](../HOST-TOOLS.md). They do not weaken host policy or authorize a
same-user hostile process; the trusted operator controls the recovery identity.
