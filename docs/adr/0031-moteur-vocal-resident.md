# 0031 — Warm local voice and system audio defaults

Date: 2026-09-29. Status: accepted. Audio routing supersedes ADR 0027.

Repeated speech requests started a new interpreter and loaded the same verified
weights. Short consecutive exchanges paid this cost again. The operator also
requests automatic operating-system input/output selection instead of device
pickers in Welcome and AURA.

The API starts one optional private voice subprocess on demand. It exchanges
bounded JSON lines through inherited pipes; no listening socket is added.
Only synthesis and transcription are accepted. Text never enters process
arguments or logs. Native library diagnostics are suppressed. A malformed or
oversized response terminates the worker; cancellation kills its process group
and releases the lease and transient files before another exchange can proceed.
API shutdown also stops it. The worker exits after five idle minutes, and the
bridge conservatively replaces it before reuse after four minutes.

The resident process retains at most two recognition models and one synthesis
session. Pinned model hashes are still checked for every operation. Recognition
settings, French FP32, English INT8, onset padding, VAD, pronunciation and pause
policies are unchanged. No audio, answer or conversation-result cache is added.
The existing one-shot voice CLI remains usable for offline work and media builds.

This trades bounded idle RAM for lower warm latency. The first exchange can still
be slow; five minutes without voice returns to cold startup. It remains sequential
turn-taking, with explicit stop controls, rather than full-duplex speech. Native
model tests qualify precision separately from small local timing measurements.

The browser always requests the default microphone with standard echo/noise/gain
processing. Old saved device identifiers are removed and ignored. Playback uses
the system output and keeps synchronous `play()` on the default path, preserving
browser gesture activation. The browser-only microphone diagnostic remains;
visiting a page never starts microphone capture. Device changes are made in the
operating system. No peripheral selector or enumerator remains in the product.

Regressions cover repeated native worker turns, bilingual recognition, strict
framing, idle exit, cancellation/restart, model-cache bounds, legacy preference
migration, permission recovery, playback activation and stale response rejection.
Physical microphone quality and perceived naturalness still need operator listening.
