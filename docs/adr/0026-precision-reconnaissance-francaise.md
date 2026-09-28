# 0026 — French recognition precision

Status: Accepted, 2026-09-28. Refines the French compute choice in ADR 0020.

## Context

CI for `87796e38` passed on AMD EPYC but failed on Intel Xeon 6973P-C: the
synthetic greeting transcribed “La plateforme protège vous donner” instead of
“La plateforme protège vos données”. Local AVX2 dispatch reproduced the exact
error. Native local dispatch passed on the same WAV. The waveform and lexical
assertions are now preserved in `tests/fixtures/french-data.wav`.

Using the same WAV, model, decoding hints and CPU limits, INT8 beams of 5, 10
and 20 all failed. Float32 inference with the existing beam of 10 passed. This
isolates an inference precision/dispatch sensitivity for this signal, rather
than a missing microphone sample or a corrupted media container.

## Decision

Use `compute_type="float32"` for French only. Keep English INT8, existing model
aliases and pinned files, oneDNN bootstrap, four CPU threads, one worker, VAD,
beam size and lexical hints. Do not rewrite words after recognition or route
audio externally. This is an inference change, not model fine-tuning.

Run the preserved French fixture in WAV and both Opus containers during native
and forced-AVX2 CI. Keep the newly synthesized bilingual suite and the original
English regressions. Failed CI captures contain only synthetic test media and
expire after seven days; user recordings are never uploaded as diagnostics.

## Alternatives rejected

- Accepting “vous donner” in the test would hide the reported lexical defect.
- Increasing the decoding beam did not correct this signal.
- Forcing a processor instruction set in production would unnecessarily restrict
  hardware and would not establish language accuracy across other inputs.
- Replacing or enlarging the model adds downloads and memory costs without a
  demonstrated need for this repair.

## Consequences

Float32 can consume more memory and time than INT8. On this workstation under
AVX2, the single preserved recording took 3.573 seconds instead of 2.557 seconds
including model verification/loading. These are individual measurements, not
latency percentiles. Existing process deadlines and concurrency limits remain.

Passing a synthetic corpus does not certify accents, physical microphones,
negation handling in every sentence or all processors. Review transcriptions
before sending consequential instructions; tool execution remains separately
controlled by the platform's approvals.

The upstream [CTranslate2 quantization documentation](https://opennmt.net/CTranslate2/quantization.html)
supports explicit inference compute types, including float32 with existing
converted weights. It does not promise identical recognition across processors;
the decision here rests on the preserved local and hosted regression evidence.
