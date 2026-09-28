# ADR 0027 — Explicit browser-local audio routing

Date: 2026-09-28. Status: accepted. Supersedes the system-default-only UI decision
in the 0.4.1 recovery for operators who explicitly select a device.

## Context

The operator still cannot capture a physical microphone reliably. OS defaults
can point to a virtual or inactive input. A system-default-only interface cannot
explain or correct that choice, and separate media players must agree on output.

## Decision

Expose an accessible, themed audio panel in AURA and Welcome. Enumerating devices
does not itself request capture. **Detect devices** is an explicit permission
gesture, opens a stream only briefly, and stops every track including late
permission grants after cancellation. Native selects preserve keyboard behavior.

Store input/output identifiers and processing preference only in browser storage,
with an in-memory fallback. Never transmit them to the API or logs. Ignore the
obsolete device preference key, whose stale identifiers caused past regressions.
Use an exact input constraint for an explicit choice: do not silently fall back
to another microphone. Device changes refresh the inventory; a missing selected
device remains visible until the operator chooses a replacement. Lock input
changes during recording and discard diagnostic samples when the input changes.

Route all native audio/video players through one shared output module. Serialize
per-player `setSinkId` operations; re-check the latest choice before playback;
route existing playback when the choice changes. Preserve synchronous native
play on the unchanged/default path. Cancellation must prevent late routing from
starting playback. Failed routing pauses playback and exposes a recovery message.

Feature-detect speaker selection and the optional browser output picker. An
unsupported browser offers system output rather than pretending a choice worked.
Browser authorization, secure context and autoplay rules remain authoritative.
Microphone analysis stays connected to an inaudible sink; background music yields
to diagnostics and speech. No live microphone is looped into speakers.

## Verification and limits

Unit tests cover exact constraints, missing devices, denied permissions, output
serialization, cancellation and resource cleanup. Playwright combines synthetic
device inventory with native MediaRecorder, media decoding and playback. Its
virtual speaker adapter calls the real default sink: it tests UI routing, not a
physical USB headset. Physical Windows input/output acceptance remains necessary.

## Primary references

- [Device enumeration and permission limits](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/enumerateDevices)
- [Media output selection and permissions](https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement/setSinkId)
- [User-initiated speaker authorization](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/selectAudioOutput)
