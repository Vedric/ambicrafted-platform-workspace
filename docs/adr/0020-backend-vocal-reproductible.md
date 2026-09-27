# 0020 — Explicit CPU backend for local speech recognition

Status: accepted, 2026-09-27.

## Context

The hosted speech job for push `157077e6` failed one of fourteen real offline
tests: the frozen confidentiality WAV produced “custom and data” where the
synthetic source says “customer data.” The pull-request job for the same head
passed all fourteen. Both downloaded the same SHA-pinned artifacts and used
the same dependency lock and Ubuntu image revision. The frozen input excludes
Piper synthesis variability as the cause of this particular failure. The
original logs did not record CPU vendor or native backend, so they cannot prove
which backend either runner selected.

The failure was then reproduced locally on the same AMD CPU by changing only
the CTranslate2 backend selection: INT8 with forced MKL failed confidentiality;
INT8 with oneDNN passed. The greeting fixture passed with both. A separate
float32 candidate also failed confidentiality and was rejected. No expected
word was added to a hint, and no fixture or lexical assertion was relaxed.

The [CTranslate2 environment documentation](https://opennmt.net/CTranslate2/environment_variables.html#ct2-use-mkl)
states that automatic MKL selection depends on CPU vendor and that environment
configuration must precede native import. Its
[quantization documentation](https://opennmt.net/CTranslate2/quantization.html#quantize-on-model-loading)
allows changing compute type when loading existing weights; that supported
alternative did not fix this observed recognition error.

## Decision

Set `CT2_USE_MKL=0` in the voice runtime bootstrap, `hors_ligne()`, before importing
faster-whisper/CTranslate2. On the supported x86-64 Linux wheel this selects
oneDNN instead of vendor-dependent MKL dispatch. Override a conflicting inherited
value: operators should not silently change the qualified inference path.

Retain the existing INT8 compute type, four CPU threads, one worker, ten-candidate
beam, 400 ms acoustic context, VAD, domain hints, language aliases and model
artifacts. Both languages still run locally, without GPU use or runtime network
access. No extra download or dependency is introduced.

The supported execution boundary remains a fresh voice CLI subprocess per
operation. An embedding application that initializes CTranslate2 before calling
our bootstrap can cache a different native backend; changing the environment
after that initialization is not a supported reconfiguration mechanism.

## Verification and consequences

The explicit oneDNN candidate was compared with the already fixed signals:
eight original corpus phrases, eight additional phrases and the two regression
fixtures. All sixteen corpus transcripts were identical to the prior qualified
INT8 results. Both regression fixtures passed. Fifteen of eighteen automatic
anchor sets passed; the three other cases were unchanged: two existing French
errors concerning network latency and the homophone “paie/paix,” plus an English
punctuation-only mismatch in “test, environment.” This is a regression check,
not a general word-error-rate or microphone accuracy claim.

Private evidence outside Git preserves both hosted job logs, the original
engine revision, the evaluation script, WAV hashes and all candidate results
under `immersive-2026-09-27/voice-ci-157077e6/`. The oneDNN run completed eighteen
transcriptions with a median of 2.080 seconds, including model verification and
loading in the test process. This is a workstation observation, not a latency
guarantee. The float32 run partly overlapped the MKL experiment and must not be
used as an isolated performance comparison.

Tests enforce bootstrap ordering before the native import and exercise real
CLI subprocesses given `CT2_USE_MKL=1`, preserving the onset and confidentiality
assertions. Hosted offline tests must still pass on new runners before release.
Their diagnostics record only CPU identity, CTranslate2 version, supported
compute types and selected configuration. No credentials, environment dump,
operator audio or customer text may enter those diagnostics.

A fixed library backend reduces this observed dispatch variation; it does not
promise identical floating-point operations on all processors or eliminate
speech-recognition errors. Manual transcript review remains the default, and
spoken text never grants approval for operational tools.
