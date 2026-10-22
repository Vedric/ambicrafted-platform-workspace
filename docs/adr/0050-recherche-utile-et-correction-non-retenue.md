# ADR 0050 — Clarify source exploration; decline unproven automatic repair

Date: 2026-10-22

Status: Source-exploration clarification implemented; qualification recorded
separately. Automatic repair experiment not adopted.

## Context

The local workflow still makes substantive reasoning errors. Its exact-source
guard proves where a proposed instruction came from, not whether its diagnosis
is correct. The additional AI consistency review is fallible and can reject a
useful proposal. Neither guard removes the need for the operator's judgement.

Some runs repeatedly searched procedures even though the actual missing evidence
was an incident measurement, log, approval record or restored attachment. The
previous prompt also suggested both lexical and semantic searches whenever in
doubt, which could encourage unnecessary work before reading a relevant result.

## Decision

Clarify the existing investigation instructions: choose the appropriate search,
read a relevant candidate, and make another search only for a remaining procedure
question. Ask for absent observations in the missing-evidence field. Searching
runbooks cannot establish an unrecorded measurement or approval. Do not reread an
unchanged source.

The existing source guard, bounded exploration, token/deadline accounting,
confidential local routing, exhaustive consistency review and durable human gate
remain unchanged. A failed review still produces an explicit abstention; the
workflow never executes remediation.

Do **not** ship the automatic repair prototype tested during this qualification.
It permitted one tool-free correction after a usable review refusal and subjected
the result to the original guards. It correctly bounded its attempts, but a
six-case comparison demonstrated no successful repair attributable to this
mechanism. Adding two potential calls and another state transition without an
observed usefulness benefit is not justified for the personal release.

## Alternatives rejected

- Removing or relaxing the review to increase apparent pass rates: would hide
  established errors.
- Repeatedly reviewing the same proposal until a model agrees: would select
  favorable stochastic outcomes without better evidence.
- Shipping the bounded correction merely because its contract tests pass:
  mechanical safety tests do not demonstrate practical usefulness.
- Case-specific keyword rules: would fit examples without establishing general
  reasoning quality.

## Consequences and evidence

The retained change is small and does not introduce a new retry loop or quality
metadata contract. Its effectiveness must be assessed independently of the
discarded prototype. A single comparison per case is stochastic engineering
evidence, not a general accuracy estimate.

The private qualification record preserves the baseline, prototype, source
hashes, unsuccessful repair, token counts and review decisions. A separately
declared prompt-only comparison checks the actual retained implementation.
New cases are sealed before exposure, evaluated after a signed source freeze,
and become regressions once inspected. The current qualification document
records results and remaining limits; AI engineering review is not independent
human acceptance.

A future repair design needs evidence that it improves useful, correctly
grounded answers under the same budget without hiding refusals. Until then,
explicit abstention and a human review are preferable to extra automatic calls.
