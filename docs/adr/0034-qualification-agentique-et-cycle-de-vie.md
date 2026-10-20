# ADR 0034 — Qualification agentique et cycle de vie séparés

- Date: 2026-10-20
- Status: accepted

## Context

The four local model checks covered simple contracts. They established neither
representative engineering quality nor sustained control-plane operation.
Mission profiles are not independent agents. Good retrieval or an exact citation
does not establish the correctness of a diagnosis.

## Decision

Qualify the production workflow through a separate synthetic evaluation corpus,
initially 39 cases covering SRE incidents, infrastructure reviews and change
reviews. Each case supplies sources and a substantive rubric. Maintain regression
and held-out sets; a case used to tune a prompt must no longer be presented as
an independent generalization observation.

The runner invokes the real LangGraph CLI and actual MCP tools through NEXUS.
It uses only the local alias and an already-loaded confidential key, a temporary
corpus and checkpoints, and a separate disposable Qdrant instance for semantic
retrieval. Errors, timeouts and incomplete cleanup are explicit failures. No
proposal is automatically approved. Input hashes and exact scope accompany each
result; source drift during a run invalidates its mechanical qualification.

Separate deterministic checks (human gate, tools, exact provenance, abstention)
from reasoning quality assessed against a rubric. A review is bound to the exact
result hash; contract success is not a product acceptance. An external LLM judge
is excluded from this confidential workflow and cannot substitute its judgment
for ground truth. AI engineering reviews are supporting analysis, not independent
human acceptance.

Replace the supported Promptfoo installation with the existing-environment,
standard-library local runner. The broad provider dependency tree introduced
unnecessary vulnerabilities, including a vulnerable transitive package without
a fixed release. Preserve the historical YAML as clearly identified, inert
archives; they are not a supported executable comparison. External-provider
comparison is removed from supported installation until a separately reviewed,
secure and explicitly authorized implementation exists. The npm entry point only
forwards documented runner arguments; offline tests never invoke a model.

Initial real-model runs revealed an unsourced procedure in classifier free text,
displayed before human approval. A stricter prompt did not prevent recurrence.
Both engines now retain only the three typed triage estimates and derive a fixed
explanation preserving uncertainty and the absence of execution authority. The
UI presents equivalent English/French wording, including for historical reports,
instead of rendering their old free text. Priority remains an estimate requiring
verification. Detailed reasoning belongs in the sourced proposal for human review.
A separate causal-precedence instruction addresses a discovered reverse-timeline
error; the new rule remains a mitigation to evaluate, not a guarantee.

A second campaign exercises the real HTTP control plane and disposable SQLite
state, with deterministic inference subprocesses. It can run for 24–72 hours
without consuming GPU capacity and covers queueing, cancellation, budgets,
failures, decisions and graceful restart. It does not replace a sustained test
with a real model. One worker remains alive during the measured period so that
frequent restarts do not conceal resource leaks.

Add critical UI journeys for Firefox and WebKit while retaining desktop/mobile
Chromium. Include motion preference and welcome/AURA animation qualification.
Physical media and Safari on actual devices remain separate acceptance work;
a Linux WebKit engine does not qualify every Safari/iOS version.

## Consequences

No new framework or permanent service is required. The scripts use the standard
library and existing locked environments. Artifacts remain private, synthetic
and outside Git. Failures provide evidence to investigate, not expectations to
weaken merely to obtain a green result. When a fixture itself lacks its intended
procedure, preserve the initial failure and explain the corpus correction.

The fixtures are deliberately limited and include hostile instructions that must
never enter operational runbooks. Reasoning quality, voice performance, customer
isolation and recovery after host loss have distinct acceptance criteria. Every
release must identify completed tests, their exact parameters and limitations;
a started 24-hour job is not a completed soak test.
