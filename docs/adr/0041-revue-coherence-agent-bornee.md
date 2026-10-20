# ADR 0041 — Bounded consistency review of agent proposals

Date: 2026-10-21

Status: Implemented; development evidence recorded, frozen-revision qualification pending

## Context

The 51 synthetic missions and subsequent five-case runtime smoke exposed errors
that the existing source guard cannot detect. A complete runbook paragraph proves
where an action came from, not whether a diagnosis is correct. Observed failures
included arithmetic and denominator errors, planned changes described as applied,
comments described as executed attacks, unsupported causal attribution and an
extraction contradicting a more careful final answer. Another prompt incorrectly
treated ordinary imperative requests for help as injection attempts.

All 51 previously examined cases are regression evidence for this change. Their
expectations must not be weakened, and their earlier holdout status does not carry
forward. Acceptance requires new unseen cases after implementation freeze, plus
an explicit human review. AI reviews do not satisfy that requirement.

## Decision

Both SRE engines use one shared quality boundary after source validation and
before delivery or the durable human approval pause. It makes at most one
additional local, confidential model call per final proposal. The call uses the
same restricted gateway key, token accounting, deadline and cancellation boundary
as other calls. It cannot request tools or initiate another reasoning loop.

The review receives the original observations in invocation memory, the derived
extraction, the proposed diagnostic and the selected runbook actually read. Its
input and response are not appended to checkpoint messages. Source quotations used
for arithmetic remain transient. Existing generated model messages remain
confidential and can contain repeated identifying information; this is not an
anonymisation guarantee.

The closed schema permits only:

- One explicit verdict for **every** code-indexed proposal field: no material
  discrepancy found, quantity, chronology, execution status, attribution, scope or
  absent proof. Code requires exhaustive, unique coverage; missing, repeated or
  unknown references make the review unusable.
- Bounded arithmetic checks referencing a registry of literal original operands.
- A maximum confidence of low or medium, and a judgement about evidence sufficiency.

Proposal modalities are supplied by code from their application fields. Requested
information and future actions are not automatically treated as completed events.
Their factual premises still require scrutiny. The source guard's own appended
finding is excluded only when the caller has just observed that guard decision;
the count of rejected actions is passed as application context. Identical text
supplied by the model receives no exemption. No business keyword or copied warning
is used as a provenance shortcut.

It cannot provide a replacement cause, actions or arbitrary remedial prose. Code
builds the proposal/operand registries from exact input fields and literal spans;
the model selects opaque references and cannot redefine their values or units.
This avoids accepting invented citations or rejecting a valid value because the
reviewer paraphrased its surrounding sentence. Scalar parsing is
bounded and uses explicit supported units, Decimal arithmetic and ISO timestamps
with a timezone. Supported operations are comparison, ratio as a percentage,
relative change and difference. At most four calculations can reuse an earlier
numeric result with its computed dimension; forward references, cycles, unknown
references and reuse of a comparison as a number are refused. No expression
evaluator or business-keyword rule
engine is used. Unknown units, truncated values, missing units, incompatible
dimensions, ambiguous decimal/thousands notation, excessive precision, a zero
denominator or an unknown reference fail closed. Registries are capped at 48
proposal fields and 64 literal operands; exceeding a cap causes explicit
abstention rather than silently dropping evidence. Results are
rendered by code, never paraphrased by another model. Numeric result checks are
exact; rounded claims can be refused and this availability cost must be measured.

A material final discrepancy, a declared calculation contradicted by code, an
invalid review, missing original evidence or unavailable review causes an explicit
abstention with no diagnostic cause or action delivered. A budget/deadline failure
continues to use the existing budget-exhausted outcome, without a partial diagnosis.
An error limited to the extraction removes its unreliable summary rather than
rewriting it; a consistent final answer may still be retained. Confidence can only
decrease. Identifying a missing document is not evidence of high confidence in the
state of the real system.

`Diagnostic.qualite` records the application-produced status, discrepancy codes,
computed arithmetic, extraction suppression, review latency, observed review tokens
and explicit limits. Legacy reports without this field remain readable. The UI
and exports must call this an **AI consistency review**, never a general verification
or independent approval.

Checkpoint contract version 3 prevents a paused version-2 proposal from bypassing
the new review on approval. Resuming such a pause returns an explicit incompatibility
message and requires a new analysis/thread; historical state remains readable and
is not deleted. Inventory pending live analyses before any runtime migration.

The injection prompt now distinguishes attempted rule overrides, secret requests
and approval bypasses from ordinary requests for analysis or quoted commands.
A detector estimate is no longer promoted into proof that observations are forged.
Read-only tools, restricted routing and human control remain authoritative.

## Limits and validation

The reviewer uses the same local model and can share its errors. Exhaustive
verdict coverage proves that every reference received a verdict, not that the
model understood it or evaluated it correctly. It can miss a
false premise, select the wrong populations or reject a valid conditional answer.
Literal provenance and correct arithmetic do not prove semantic relevance,
authenticity, clock alignment, causality or statistical significance. A clean
review is not proof that every claim was checked. No code path promises zero
reasoning errors.

Unit and boundary tests must exercise both engines, real schema validation and
gateway accounting with only external responses substituted. Negative cases cover
forged/truncated operands, units, zero denominators, exact arithmetic, schema
violations, contradicted claims despite an optimistic reviewer, unsupported
execution/attribution, missing evidence, restricted routing, deadline/tokens,
non-persistence and historical checkpoint refusal. Retained valid answers, unchanged
actions and confidence monotonicity provide positive controls.

Real synthetic qualification must retain previous failures, distinguish a valid
abstention from refusal of a solvable mission, and report review latency, token
overhead, usefulness and remaining false conclusions. Declining every case is not
success. Development runs are marked dirty and cannot replace qualification on a
frozen clean revision.

Development replays of ten fixed historical proposals exposed a substantial
availability regression: exhaustive untyped review rejected all ten. Typed
modalities and source-guard provenance retained five and rejected five, with
78.116 seconds total, 7.618 seconds median, 29,441 input tokens and 3,930 output
tokens for the review calls alone. These are not a full-pipeline success rate.
The canary's invented error count and unsupported statistical claim were still
missed in the relevant cause fields; other objections happened to veto delivery.
The certificate extraction was suppressed for a different objection, not for its
incorrect validity assertion. Those outcomes must not count as correct detection
of the target error. An implementing AI reviewed these outputs; no human acceptance
or independent generalisation result has been completed.

An experimental thinking-enabled call used the same 2,500-token cap, exhausted it
after 41.273 seconds and returned invalid JSON. It was rejected. The experiment
was stopped and its option removed; ordinary `reasoning_effort=none` is unchanged.
No quality or performance claim is made for the unexecuted remaining comparisons.

An independent loopback server demonstrated that periodic HTTP bytes could extend
the old inactivity timeout beyond the run deadline: 665.7 ms with a 150 ms deadline.
The HTTP boundary now uses `asyncio.timeout` around the complete asynchronous
exchange and closes its client on cancellation. The same probe returned after
124.2 ms and the server observed an early disconnect. When called from a running
event loop, a joined worker hosts the cancellable exchange without abandoning it
on a thread timeout. Cleanup can add scheduling overhead. Closing a proxy
connection does not prove that upstream inference already accepted has stopped.
