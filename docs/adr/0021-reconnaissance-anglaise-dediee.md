# 0021 — Dedicated recognition for short English turns

Status: accepted, 2026-09-27. Completes [ADR 0020](0020-backend-vocal-reproductible.md).

## Context

Explicit oneDNN initialization did not eliminate CPU-dependent recognition
differences. Hosted revision `d7030397` passed 16/16 real speech tests on AMD
EPYC 9V45, but passed 14/16 on Intel Xeon Platinum 8573C: the frozen
confidentiality waveform corrupted “customer data” in direct and fresh-CLI
tests. Both recorded `CT2_USE_MKL=0`. These identified processors and outcomes
do not by themselves isolate an individual ISA instruction as the cause.

Changing compute type to float32 or using the smaller English-only candidate
did not repair the confidentiality fixture. Those candidates were rejected.
No fixture, expected text, domain hint or lexical assertion was changed.

The larger English-only candidate passed the frozen greeting and
confidentiality signals under native and AVX2 execution, but replacement across
the entire 90-second input range caused omissions in a fixed 89.5-second varied
recording. In a repeated long signal it retained only four of fourteen complete
privacy prohibitions. The text-only decoding alternative made both long results
worse and was rejected, with its failures retained in the private evidence.

The [pinned faster-whisper source](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/feature_extractor.py)
defines a default 30-second feature window. Its
[transcription source](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/transcribe.py)
shows that `without_timestamps` changes the decoder prompt and timestamp-based
window advancement. It provides no guarantee against omissions. We retain the
original timestamp behavior and avoid introducing a custom chunking algorithm.

## Decision

Use the internal alias `transcription-en-courte` only for English source audio
whose decoded sample count, plus the existing two 400 ms context margins, fits
within one native 30-second window. At 16 kHz the exact inclusive condition is
`source_samples + 12,800 <= 480,000`, giving a 29.2-second source limit. Count
samples before rounding the public duration; an extra sample takes the long
route even though both durations would be displayed as 29.200 seconds.

Retain the existing `transcription-en` multilingual weights for longer English
recordings and `transcription-fr` for all French recordings. Keep their options
unchanged. Every English result still returns the public alias
`transcription-en`; the internal selection does not change the API schema.
No recording is split or stitched by this change. The 90-second input limit,
four CPU threads, INT8 compute, ten-candidate beam, VAD, lexical hints,
oneDNN bootstrap and 120/130-second deadlines are unchanged.

The short-English model is configured only in the manifest:
`Systran/faster-whisper-medium.en`, revision
`a29b04bd15381511a9af671baec01072039215e3`, MIT license. Its
[pinned upstream model card](https://huggingface.co/Systran/faster-whisper-medium.en/blob/a29b04bd15381511a9af671baec01072039215e3/README.md)
is installed with four runtime artifacts. All five sizes and SHA-256 values
are pinned, totaling 1,530,459,085 additional bytes. Weights remain outside Git,
in the private state directory `voice/transcription-en-courte`. The existing
installer verifies and atomically publishes artifacts. English readiness now
requires synthesis, baseline recognition and short-turn recognition to verify;
French readiness remains independent. Missing short-turn weights are an
explicit installation error, never a runtime network download or silent fallback.

Production imposes no CPU ISA ceiling. CI additionally runs the preserved short
regressions with AVX2 dispatch constraints, initialized before native imports.
The [oneDNN dispatcher documentation](https://uxlfoundation.github.io/oneDNN/dev_guide_cpu_dispatcher_control.html#runtime-controls)
and [CTranslate2 environment documentation](https://opennmt.net/CTranslate2/environment_variables.html)
describe separate controls; the CTranslate2 ISA variable alone does not limit
the backend library. Hosted validation is required before delivery.

## Qualification and limits

A fixed 29.044444-second waveform combines four complete existing utterances
about network latency, confidentiality, job counts and dates, separated only by
three 200 ms gaps. Selection, source hashes and criteria were frozen before its
two transcriptions. Both baseline and candidate retained all four statements,
negations, approval requirement, 42 jobs and three workers. Raw anchors were
16/16 versus 14/16: the candidate rendered times as `1430`/`1515` rather than
the separators expected by the unchanged checks. The values remained correct;
the raw failed checks are preserved separately from their interpretation.

An independent six-phrase holdout scored 4/6 baseline and 5/6 candidate under
both native and AVX2 execution. Nevertheless, the candidate additionally
changed `runbook` to `rumble` in an already misrecognized sentence, with other
read/quote errors. This is an explicit regression and a reason to retain
manual review, not a claim of universally improved recognition. Longer English
input preserves the baseline behavior, including an observed confidentiality
word error; French errors such as the paie/paix homophone remain possible.

On the reference workstation, the near-boundary recording took 5.196 seconds
with the baseline and 10.804 seconds with the candidate, including loading and
hash verification. Fresh-process peak RSS was 710.8 versus 1,595.3 MiB.
Short regression calls took approximately 5–7 seconds. An independent process
making six candidate calls reached about 2.5 GiB; this is not a per-request CLI
peak. The API serializes voice work and continues to terminate each operation's
subprocess group on deadline or cancellation. Prior English latency figures
are historical and must not describe the new short-turn route.

Boundary tests exercise a real decoded WAV at the inclusive cutoff, one extra
sample and unchanged French routing, while asserting stable public aliases
and timestamp options. Readiness tests cover an absent short model. Existing
real greeting, confidentiality, codec, silence and inherited-environment checks
retain their assertions. Hosted native/AVX2 runs and the real browser flow must
qualify the final commit independently of this workstation investigation.

All evidence is synthetic and private outside Git under
`immersive-2026-09-27/voice-ci-medium/` and `voice-holdout-six/`, including failed
candidates and full available transcriptions. This does not measure accuracy
on a physical microphone, accents, noise or arbitrary utterances. Manual review
remains the default; opt-in conversation may forward an inaccurate transcript.
Speech never grants authorization to operational tools.
