# ADR 0009: verifiable guarantees after the audit

Date: 2026-09-26. Status: accepted.

## Context

The audit of `ebb7aa94` reproduced differences between documented guarantees
and observable behavior: implicit declassification, declared-only sources,
actions delivered after refusal, state reuse and unconstrained file reads.
This ADR supersedes the affected parts of ADRs 0002, 0003, 0004 and 0005.

## Decision

1. The SRE pipeline is entirely local. Extraction, triage, reasoning and
   embeddings use local aliases and the confidential key. An extraction
   remains confidential; no automatic external-export mode is provided.
   External gateway aliases remain available for separate public/synthetic work.
2. Provenance comes from the reader, not model assertions. The MCP read
   envelope contains filename, actual text, SHA-256 and truncation status.
   Only a complete verified read populates the registry. Proposed actions
   must match whole paragraphs after whitespace normalization; removing a
   negation or prerequisite from a paragraph is rejected. Relevance to the
   incident still requires human review.
3. Proposal and delivery are distinct. Pending/rejected graph reports have
   no deliverable diagnosis. The approval preview includes uncertainties
   and injections. Structured approval requires boolean `true`. A new
   incident requires a new thread, not reuse of previous state.
   Checkpoints carry a delivery-contract version. Older checkpoints cannot be
   approved under the new contract; re-analysis requires a fresh thread.
4. The raw alert is held in invocation memory, not the checkpoint schema.
   Derived extracts, quotes, tool results and messages remain confidential
   and may retain identifiers. They persist locally with a 14-day inactivity
   policy enforced by a daily user timer. A crash before extraction requires
   new input; the later human gate remains durably resumable.
5. File access is bounded and refuses symlinks/non-regular files at open time.
   Text search is literal. Semantic search applies a conservative score
   threshold and refuses stale corpus fingerprints.
6. Index publication uses a new physical collection and atomic alias switch
   after validation. Historical `runbooks` is preserved during migration to
   `runbooks-current`. Old versions provide rollback and need explicit cleanup.
7. Unit and cumulative costs use different attributes. `ambicrafted.cost_usd`
   is for LLM spans; `ambicrafted.run.cost_usd` is the root total. Node budget
   snapshots are non-additive. Expected human pauses are not trace errors.
8. Implicit LangSmith telemetry is disabled before orchestration imports.
   Tool arguments, HTTP response bodies and validation inputs are not copied
   into agent error traces. Export destinations remain an operator-owned policy.
9. Operational tooling provides safe key creation, health/digest checks,
   coherent local backups, isolated restore drills and daily retention.
   Backup files contain secrets and have the same 14-day lifecycle. They are
   never repository artifacts or sent to external scanners.

## Alternatives rejected

Regex anonymization cannot prove that arbitrary free text contains no customer
information. An external reasoning switch would retain that ambiguity, so it
is not the current incident-data path.

SQLite already covers incident resumption and Qdrant covers document retrieval.
No graph query or cross-incident memory requirement currently justifies Neo4j.
Adding it would create another copy of sensitive data needing partitioning,
backup and deletion. Revisit with a concrete query and isolation model.

Source existence alone does not verify an action. Arbitrary substring matching
can drop a negation or condition. Whole-paragraph matching is deliberately
stricter, although it still cannot prove semantic relevance or corpus accuracy.

## Consequences and evidence

Local reasoning consumes GPU memory and may be slower. Plausible paraphrases
are rejected; runbooks need self-contained actionable paragraphs. The agent
keeps its four read-only tools and gains no automatic remediation authority.

Offline tests now cover the audit counterexamples, source-envelope integrity,
negation/prerequisite preservation, human refusal, thread reuse, expected-pause
trace status, malformed embeddings and failed index publication. Real-service
checks separately verify image startup, routing restrictions, retrieval and
recovery. Neither class of test proves universal model correctness.

Whole-workstation availability and remaining upstream image findings remain
limitations. No percentage-complete or zero-risk claim follows from this ADR.

Sources: [atomic Qdrant aliases](https://qdrant.tech/documentation/manage-data/collections/#collection-aliases),
[LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence).
