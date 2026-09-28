# ADR 0028 — Réactivité des conversations et mouvement continu

Date: 2026-09-28. Status: accepted for the private workstation.

## Context

AURA could wait for 90 seconds when continuous input energy prevented end-of-turn
recognition. The first real-browser probe also exceeded 120 seconds before audible
output while the local model was loading. Warm probes still needed 34.7 seconds in
English and 24.1 seconds in French from Record start to native playback. The existing
rotations (44–100 seconds) were too subtle, and large reveal parents swallowed child
entrance animations.

## Decision

Prepare the confidential `local` alias on authenticated AURA entry, using a fixed
one-token request and the existing inference lease. Keep the microphone off until
readiness and explicit user activation. Bound preparation, cancel it on disconnect,
show failure and offer manual retry. Ask the runtime for 24-hour retention. Ollama's
[official FAQ](https://docs.ollama.com/faq#how-do-i-keep-a-model-loaded-in-memory-or-make-it-unload-immediately)
documents retention; the [LiteLLM Ollama integration](https://docs.litellm.ai/docs/providers/ollama)
remains the model boundary. The running instance's expiry confirmed forwarding.

Use a recent-peak-relative energy floor while preserving quiet input, around 1.1
seconds of silence and a hard 30-second conversational turn. This remains energy
measurement, not semantic voice activity detection. Keep manual 90-second recording.
Spoken replies use a strict `vocal` flag, 1–3 sentence / 55-word instruction and 220
output tokens, with the same authority/context. Include the flag in idempotency;
preserve preexisting text-mode fingerprints and the original mode on UI retries.

Bound conversational STT/TTS to 30 seconds and dialogue to 45 in the browser. Abort
requests, invalidate late continuations, preserve drafts/completed written replies,
and cancel speech subprocess work when the caller disconnects. Await ASGI receive
directly after body parsing: `Request.is_disconnected()` can absorb task cancellation
inside its AnyIO cancellation scope, which a real API regression test exposed.

Use CSS-only rings, breathing, waves and heartbeat at rest. Continue measuring real
audio separately. Pause animation offscreen, in hidden tabs, on operator pause or OS
reduced-motion preference. Fade individual visible children without transforms on
observed containers; do not hide content awaiting JavaScript or change click geometry.

## Alternatives rejected

- Cloud failover: not necessary for the observed failures and would change the
  workstation's confidential boundary.
- Faster but less accurate recognition models or reduced precision: previous frozen
  speech regressions make this an unjustified shortcut.
- An always-running multi-process speech pool: additional lifecycle and privacy
  complexity; current improvement does not require a new daemon.
- Fake signal energy or perpetual page-wide JavaScript loops: decorative motion must
  remain distinct from actual audio and suspend when not visible.

## Consequences and verification

Cold loading is visible before recording rather than hidden after a spoken question.
Retaining the model occupies GPU memory longer and cannot prevent eviction by other
workloads. Opening AURA makes one local synthetic model request; no microphone audio
or conversation content is sent during preparation. Thirty-second spoken turns can
split long monologues; manual mode remains available. Timeouts improve recovery,
not inference speed or recognition accuracy. No simultaneous listening/speaking is
claimed.

Tests cover quiet input, background noise, never-ending input, stalled stages, late
results, authenticated preparation, cancellation through the actual ASGI boundary,
idempotency and complete cleanup. Browser qualification checks Welcome/Overview/AURA
motion, both scroll directions, native recording/playback, responsive layouts,
reduced motion, keyboard access and light/dark themes. Measurements and remaining
limits are recorded in [RELEASE-0.4.3](../RELEASE-0.4.3.md).
