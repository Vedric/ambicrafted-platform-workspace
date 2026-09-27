# ADR 0013 — English default voice with explicit French selection

Date: 2026-09-27
Status: Accepted

## Context

The private console now uses English throughout its navigation and controls.
Its existing speech pipeline synthesized and recognized French only, which
made English interaction inconsistent. The operator requested a high-quality
female English voice while retaining French, with all audio processed locally.
The GPU remains reserved for local agent and assistant inference.

## Decision

Add the runtime alias `voix-feminine-en` and make `en` the default for synthesis,
recognition and assistant conversation. Keep `fr` explicit and retain its
existing `voix-feminine-fr` artifacts and synthesis settings. The selected
English model is Piper's US female high tier based on LJ Speech, published by
Bryce Beattie. Provider/model source names remain confined to the artifact
manifest and documentation; executable code selects aliases.

The publisher identifies the English model itself as public domain, and the
LJ Speech dataset identifies its recordings and annotations as public domain.
We preserve attribution and install the pinned model card. The alternative
Lessac high candidate was rejected because its cited Edinburgh dataset source
limits use to noncommercial research. The existing Piper runtime remains
GPL-3.0, with its redistribution obligations unchanged.

The new ONNX artifact is 114,199,011 bytes, SHA-256
`5d4f08ba6a2a48c44592eed3ce56bf85e9de3dd4e20df90541ae68a8310c029a`, at
upstream revision `c10ece1aade47bb51c153c893d14e5bf8e5b7117`.
Its config and model card have independent exact sizes and hashes in
`apps/voice/src/voix_locale/modeles.json`. All downloads use the explicit
installation command; inference remains offline with hash verification before
loading. Binaries stay outside Git and backups, in private state directories.

`transcription-en` and `transcription-fr` select the existing multilingual
recognition model with an explicit language argument. Their manifest entries
share one directory and identical files; there is no duplicated recognition
download or language translation service.

The CLI accepts `--langue en|fr` on `statut`, `parler` and `transcrire`. HTTP
request bodies accept the optional `langue` field for speech and dialogue, and
status accepts the corresponding query parameter. Omitting it remains valid
and now selects English. Unsupported values fail before media file access or
inference. Readiness is cached per language; it never reuses French readiness
as evidence that the English artifacts are installed.

The assistant, AURA, identifies itself as a local AI and uses the confidential
local model alias only, English by default,
with the selected reply language in its system instructions. Explicit user
language requests can adjust prose but cannot grant tools, action execution or
approval authority. The English interface, source material language, selected
reply language and selected speech voice are separate concerns.

## Responsiveness and limits

English synthesis uses the high model on four CPU threads with natural timing.
The subprocess design retains bounded memory/output, hard external deadlines,
cancellation, one active voice request and private temporary media cleanup.
The UI can cancel synthesis or playback and must offer an explicit recording
stop and editable transcription. Manual sending is the default; an explicitly
enabled conversation mode may automatically send each completed transcript,
play the reply and resume recording in a new turn. Automatic reply playback is
opt-in. Spoken assent never approves an infrastructure operation.

We keep full bounded WAV responses instead of adding a long-lived model daemon
or streaming protocol. This avoids a second service lifecycle and preserves
the established process isolation. The measured English synthesis median was
1.794 seconds and recognition median 3.377 seconds across six synthetic round
trips with two concurrent component clients. These include startup and model
verification and are not production latency guarantees. The API still admits
one voice operation at a time.

## Validation

The model was actually downloaded, verified and used with networking disabled.
Both languages passed synthesis-to-recognition through WAV, WebM/Opus and
Ogg/Opus, along with silence tests and the existing media/file safety suite.
The isolated suite passed 59 tests, including ten real-model tests. API tests
cover default English, explicit French, rejected languages, per-language status
caches, local-only dialogue requests and preservation of authentication,
CSRF, concurrency, cancellation and cleanup.

The voice/assistant API suite passed 59 tests. Real local model requests also
verified AURA's identity, selected reply language and absence of action execution.
Observed dialogue times were 60.636 seconds for the first English request,
5.702 seconds for the subsequent French request, and 1.047 seconds for repeated
English. Initial waiting time must be communicated; these measurements alone
do not identify the reason for the slower first response.

The synthetic English load probe also exposed imperfect recognition of short
words. Its success counter requires nonempty output, not an exact transcript.
We retain manual review as the default and do not claim microphone/accent/noise accuracy or
an independently validated perceptual-quality score. See [VOICE.md](../VOICE.md)
for repeatable commands and source links.

## Primary sources

- [Voice publisher and model licenses](https://brycebeattie.com/files/tts/).
- [LJ Speech dataset and recording credits](https://keithito.com/LJ-Speech-Dataset/).
- [Pinned English model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/en/en_US/ljspeech/high/MODEL_CARD).
- [Rejected candidate's dataset license](https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/license.html).
- [Piper runtime and GPL license](https://github.com/OHF-Voice/piper1-gpl).
