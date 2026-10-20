# 0038 — Observations originales éphémères et sorties contraintes

Date: 2026-10-20

Status: accepted; semantic qualification remains incomplete.

## Context

The 39-scenario real local-model qualification on commit
`1fb46446acc80f0203e9f779d09cde75df3eb6a5` passed 33 mechanical contracts.
Three scenarios failed during extraction validation; three exhausted bounded
tool or token budgets. An explicit AI engineering review, distinct from human
acceptance, also found invented premises despite exact source attribution:
measured baselines became accepted thresholds, proposed changes became executed
incidents, and zero observed errors became an elevated error rate in a summary.
The deterministic source guard proves paragraph provenance, not relevance or
causal correctness.

Previously reasoning received only model-produced extraction. It could not
compare a faulty summary against the original observations. The incident-only
prompt also encouraged a causal diagnosis for infrastructure and change reviews
that described no observed failure.

A private synthetic reproduction isolated one concrete shape defect:
`infra-stale-design` generated `requete_researche` instead of required
`requete_recherche` in three consecutive calls. The other two initial validation
failures did not reproduce in three isolated calls each; their original failed
fields remain unknown. We do not infer their cause from the generic masked error.

## Decision

Extraction and classification request strict JSON Schema generation through the
existing confidential local gateway alias. Schemas derive from the application
models; all generation fields are required and additional fields are forbidden.
Classification generates only its three estimates, never free-form procedural
text. Pydantic validation remains mandatory after receiving a response: an
unsupported, ignored or defective generation constraint must still fail closed.
There is no permissive repair of misspelled fields and no frontier fallback.
JSON Schema mode is separate from tool-assisted reasoning.

On every reasoning call, construct a fresh message list containing the original
observations in a randomly delimited untrusted-data block. Insert it before the
assistant/tool conversation so tool response pairs stay adjacent. The graph's
invocation memory already holds the original; the manual engine now passes its
existing local argument. Never append this additional message to the durable
history, checkpoint state, or trace attributes. Human approval resumes from the
existing paused state without recovering the original or invoking a model.

The reasoning instructions identify extraction as a retrieval hypothesis, require
comparison against original observations, and distinguish an incident from a
review. The existing `cause_probable` field remains compatible: for reviews it
contains a factual assessment and conditional risk, without manufacturing an
executed change, compromise or outage. Original input remains untrusted too;
neither a log line nor an imported document grants execution authority.

The original still counts against the existing context, time and observed-token
limits. Oversized context fails before network access. This change adds no tool,
automatic remediation, model provider, persistence store or additional model call.

## Limits and tradeoffs

This removes an information bottleneck and constrains output shape; it does not
prove model correctness, causality, complete anonymisation or injection immunity.
Generated extraction, tool arguments and answers can repeat identifying details.
They remain confidential under the existing storage/access policy. Tests prove
that the application does not directly persist the added raw-input message; they
cannot prove that every model-generated derivative omits every identifier.
Gateway payload logging must remain disabled as required by the deployment
configuration.

Each reasoning request is larger. Existing ceilings remain unchanged, so a model
that searches repeatedly can still exhaust them. Safe bounded failure remains a
mission-completion failure in qualification, not a successful abstention.

The original 39 results and six failures remain historical evidence. All outputs
have now been inspected and informed engineering decisions; reruns are development
or regression evidence. A new genuinely uninspected set and independent operator
review are required before claiming fresh holdout performance or human acceptance.
No human review file is completed automatically.

## Verification

Offline tests exercise both engines through the actual HTTP adapter with
synthetic responses: local alias and schema parameters, original-versus-summary
availability, tool conversation ordering, repeated calls without history mutation,
SQLite state/files and trace attributes without the raw marker, human pause and
resume without another model request, context limits, and rejection of the
reproduced misspelled field even if a provider ignores the schema.

Real-provider qualification must record source hashes and runtime/model revisions.
Worktree measurements are explicitly development evidence; published qualification
must rerun from the exact committed clean clone. Schema compliance and semantic
review are reported separately.

## References

- [LiteLLM Ollama structured outputs](https://docs.litellm.ai/docs/providers/ollama)
- [LiteLLM JSON Schema mode and validation](https://docs.litellm.ai/docs/completion/json_mode)
- [Qualification protocol](../../evals/qualification/README.md)
- [ADR 0034 — Agent qualification](0034-qualification-agentique-et-cycle-de-vie.md)
