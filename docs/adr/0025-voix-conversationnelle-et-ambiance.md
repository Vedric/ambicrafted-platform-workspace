# 0025 — Multilingual local speech and subordinate ambient audio

Date: 2026-09-27. Status: accepted for the local private workspace.

## Context

The previous French synthesis model used French pronunciation for English product
names. Injecting English phonemes improved some terms but did not reliably render
GitHub/pipeline in a synthetic round trip. The operator wants conversational
French and English speech, the name Védric, and an original quiet instrumental.

## Decision

Use a pinned multilingual ONNX speech model with fixed female English/French styles,
behind the existing `voix-feminine-en` / `voix-feminine-fr` aliases. Keep inference
local on four CPU threads, the 2,000-character input and 120-second output bounds,
private temporary WAVs, exclusive creation and subprocess timeouts. No additional
runtime dependency is needed: ONNX Runtime, NumPy and the existing eSpeak binding
are already pinned. Installation downloads weight/style/config files from immutable
manifest URLs with byte counts and SHA-256 verification; runtime does not download.

A curated lexicon supplies English IPA for whole technical words. It preserves
the displayed answer, neutralizes user IPA blocks, maintains one speaker within
each sentence and bounds phoneme batches to 480 characters. Unsupported phonemes
raise an operator-safe error. “Bonjour Védric” is one breath group. Prompts ask for
natural concise replies; this is not weight fine-tuning or voice cloning.

Ship a reproducible original 96-second instrumental, Orbital Drift, with a CC0
dedication and signal/hash provenance. No existing score or third-party samples
are used. One shared audio owner survives route changes. Independent speech/video
leases duck the music; microphone leases take precedence and mute it. Only the
return fades up. Default background level is 0.12, capped at 0.22, multiplied by
0.08 during speech. Visibility, unmount and Escape release media/timers predictably.
Music starts only after selection, with explicit recovery for blocked autoplay.

## Alternatives rejected

Switching between two monolingual speakers mid-sentence introduces timbre changes.
A lexicon alone did not solve the observed multilingual synthesis errors. External
speech APIs would move private dialogue outside the local boundary. An existing
film soundtrack would introduce licensing and originality issues. None is used.

## Consequences

The initial comparison recovered all four target technical terms in French with
the multilingual candidate. Voice regression and additional technical cases passed;
see [VOICE.md](../VOICE.md). Browser tests observe native media playback and real
synthetic microphone streams, not physical listening quality. The shared model is
larger than the previous pair of synthesis models and still generates complete WAVs.

The model card declares Apache-2.0; retain upstream and French SIWIS attribution.
The eSpeak/Piper component retains its separate GPL obligations. The instrumental's
CC0 dedication does not relicense these components. See the
[audio notice](../../apps/console/public/audio/NOTICE.md).

No test establishes perfect human-like prosody, arbitrary accent recognition,
all-browser support, true speech streaming or simultaneous conversational barge-in.
