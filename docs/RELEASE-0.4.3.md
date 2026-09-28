# AURA responsiveness and continuous motion — 0.4.3

Console **0.4.3**, control API **0.4.1**, speech runtime **0.3.1**.
Scope: private, single-operator local use. This is not a zero-bug, instant-realtime
or commercial-production certification.

## What changed

- AURA visibly breathes, pulses, rotates and emits decorative waves continuously
  on Welcome, Overview and the voice page. Actual audio energy remains separate.
  Animation suspends offscreen, on a hidden tab, operator pause or reduced-motion
  preference. The vertical instrument and input/output selection remain.
- Welcome, AURA, guide and settings elements fade on entry and re-entry in both
  scroll directions. Large AURA/FAQ parents no longer swallow child reveals.
  Entrance animation changes opacity without moving click targets.
- Authenticated AURA entry prepares the confidential local model before enabling
  **Start conversation**. The microphone stays off. A busy or unavailable model
  offers **Prepare conversation** to retry. A cold start can take a couple of
  minutes; it is now visible before recording. Model requests ask for 24-hour
  retention; the running runtime's expiry confirmed this setting.
- Conversation capture handles low background energy relative to speech and
  sends after about 1.1 seconds of silence, with a 30-second cap even when noise
  never pauses. **Send this turn** sends sooner. Missing microphone monitoring
  falls back to a 12-second capture for transcript review. Manual **Record** still
  allows 90 seconds and requires **Send** after review.
- Spoken replies target 1–3 sentences / 55 words, with 220 output tokens instead of
  the typed response's 650-token ceiling. Context, selected documents, French
  vous, Védric and local-only/no-action boundaries are retained.
- Stalled conversational transcription/synthesis stop after 30 seconds; generation
  stops after 45 seconds. Errors name the stage. Failed generation preserves the
  draft; failed synthesis preserves the written answer. Late responses cannot
  reopen the microphone or start playback. Disconnecting cancels server work and
  releases speech/inference locks. Retrying a spoken message through **Send**
  preserves the original operation ID and mode, avoiding duplicate saved pairs.

## Real-browser measurements

Native Chromium capture from fixed prerecorded synthetic speech, real local
transcription, confidential gateway/model inference, real synthesis and native
playback. No model/speech mocks in these measurements. Only newly created synthetic
conversations were used and removed. The post-change preview used isolated state.
These are individual workstation observations, not latency guarantees.

| Observation | English | French |
| --- | ---: | ---: |
| Before: warm, capture start → voice starts | 34.7 s | 24.1 s |
| After: first complete replay | 22.0 s | 17.2 s |
| After: independent replay checking semantic anchors | 21.8 s | 18.9 s |
| After: capture start → transcription request, checked replay | 6.0 s | 6.5 s |
| After: transcription request → recognized text, checked replay | 8.4 s | 5.3 s |
| After: text ready → completed model reply, checked replay | 2.4 s | 2.3 s |
| After: reply ready → native playback, checked replay | 5.0 s | 4.8 s |

The initial cold English probe exceeded its 120-second playback wait; the model
was absent from the running-model inventory during part of that wait. Preparation
now separates that startup from microphone capture. Recognition still dominates
some English turns. The pipeline is sequential; it is not subsecond full-duplex
speech. No STT model, decoding precision or beam was weakened to improve timings.

## Verification

The regression suite covers model preparation without capture, missing/quiet/noisy
input, the capture cap, three stalled stages, late results, actual ASGI disconnects,
strict spoken-mode validation and history idempotency. Native Playwright tests also
cover microphone/speaker selection, recorded sample playback, hands-free turn-taking,
uncertain network completion followed by retry, paused/reduced motion and fades.
CI rejects flaky Playwright results even when their retry succeeds. Animation
checks observe native ready/finished operations, exercise fades at 4× CPU slowdown,
and compare document coordinates so scrolling is not mistaken for layout movement.
Synthetic audio fixtures
isolate model preparation; API tests separately enforce its real rate limit.

Local rendering measurements covered 1440/390-pixel widths, both themes, and normal
or 4× CPU throttling over six-second repeated scrolls: p95 frame time 16.7–16.8 ms,
no frames over 34 ms, no reported long tasks or horizontal overflow. Eight additional
1512/1024/768/390-pixel theme/accessibility checks reported no tested WCAG A/AA
violations or browser errors. This does not certify physical mobile performance
or every accessibility requirement. Updated README captures come from an empty
isolated workspace; provenance and hashes accompany them.

Fresh-clone qualification uses locked environments and the repository CI commands:
Python tests/coverage/lint/typing/builds/audits, real offline speech regressions,
console build/types/format/unit tests, all Playwright desktop/mobile scenarios,
evaluation configuration, secret hooks and Compose validation. Commit-specific CI
and release records are the authority for the published result; workstation artifacts
alone are not a hosted-CI claim.

## Use and remaining limits

1. Open [the local console](http://127.0.0.1:8787/assistant), or use `./plateforme ouvrir`.
2. Allow preparation to finish. Choose the conversation language and, when needed,
   your microphone/output under **Audio devices**. The local microphone test does
   not upload its recording.
3. Select **Start conversation**, speak and pause briefly. **Send this turn** is
   available if background noise holds the turn open. AURA responds then listens
   again; Escape ends the conversation. **Record** creates an editable draft.
4. If an error appears, read its named stage. A failed model request keeps your
   message; a failed voice request leaves the written reply and **Listen** retry.
   For long technical answers, use a typed question.

The physical Windows/browser microphone, headset, accent and perceived naturalness
still need operator acceptance. Longer GPU retention consumes resources and cannot
prevent eviction or restart. The input detector measures energy, not linguistic
speech. Low noise can still affect transcription; review critical material manually.

The personal-use completion conditions from [0.4.2](RELEASE-0.4.2.md#what-is-still-needed-to-finish)
remain: physical audio acceptance, representative own-workload exercises, maintained
security triage, verified restore and prolonged use. Existing documented image
vulnerabilities are not erased by this UI/voice patch. Commercial multi-user use
remains outside the delivered isolation/authentication model.

Technical rationale: [ADR 0028](adr/0028-reactivite-conversation-et-mouvement.md).
