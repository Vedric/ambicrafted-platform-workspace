# Private English and French voices

The console's local AI assistant, AURA, uses two speech engines in a separate
Python 3.13 process: a US English female synthetic voice by default, an optional French female voice,
and speech recognition explicitly configured for the selected language. Short English
turns use dedicated English weights; longer English input and all French speech
retain the multilingual weights. Speech processing
uses CPU inference with four threads per process, leaving the GPU available to
the SRE agent. The speech engine neither decides on actions nor executes tools.
The control API owns authentication, concurrency, conversation and approval.

Recognition uses INT8 computation with the oneDNN CPU backend on the supported
x86-64 Linux runtime. The engine sets `CT2_USE_MKL=0` in `hors_ligne()` before
importing faster-whisper/CTranslate2, including when an inherited environment
requests MKL. This makes the selected backend independent of the CPU vendor.
Use the supplied fresh CLI subprocess: importing and initializing CTranslate2
before this bootstrap in an embedding application can cache a different backend.
See [ADR 0020](adr/0020-backend-vocal-reproductible.md) for the controlled comparison
and remaining limits; a fixed backend does not guarantee perfect transcription
or bitwise reproducibility across every processor.

No audio, transcription or synthesis text is sent to an external service at
runtime. The browser records audio locally and submits it only to the private
control API. Do not replace this path with the browser's `SpeechRecognition`
service, which may use a remote recognition provider. The UI must request
microphone permission explicitly and provide a visible stop control.

## Installation

From the repository root:

```sh
uv sync --project apps/voice --locked
uv run --project apps/voice --locked voix-locale installer
uv run --project apps/voice --locked voix-locale statut
uv run --project apps/voice --locked voix-locale statut --langue fr
```

Installation downloads approximately 2.194 GB of public model files
(1.530 GB additional for the previous bilingual installation). It requires
network access only for this explicit step. The package's
`src/voix_locale/modeles.json` records immutable upstream revisions, exact byte
counts, SHA-256 checksums, aliases and attribution. Downloads are written to
private temporary files and published atomically after verification. Concurrent
installation is rejected. Repeating installation reuses valid files and repairs
corrupt ones.

Models are stored outside Git in
`~/.local/state/ambicrafted/voice/{synthese-conversation,transcription,transcription-en-courte}`. Set `VOICE_STATE_DIR`
to an absolute private directory to override the location. Directories must be
owned by the current user, mode `700`, without symbolic links. Model files use
mode `600`. New intermediate state directories also use `700`. Every inference
verifies model file sizes and hashes before loading them. Runtime model names in
code are only the aliases `voix-feminine-en`, `voix-feminine-fr`,
`transcription-en`, `transcription-en-courte` and `transcription-fr`; the model
manifest is the source configuration. The English long-input and French aliases
share exactly the same multilingual weights on disk. The internal short-English
alias has a separate directory and pinned model. Selecting French requires no
additional recognition download. Re-run installation after a manifest update;
English readiness requires both recognition paths to be present and verified.

`VOICE_STATE_DIR` applies to the standalone speech CLI. The control API always
uses `<PLATFORM_STATE_DIR>/voice` (the default platform state is
`~/.local/state/ambicrafted`). For a custom platform state, install the artifacts
in the same location explicitly:

```sh
VOICE_STATE_DIR=/absolute/private/platform-state/voice uv run --locked --project apps/voice voix-locale installer
```

After each code or lockfile update, run `uv sync --locked --project apps/voice`
again: the API deliberately invokes the existing `.venv/bin/voix-locale` without
resolving packages during a request. Model installation can be repeated to
verify or repair the pinned artifacts; model weights are excluded from backups.

## Control API subprocess protocol

After installation, invoke `apps/voice/.venv/bin/voix-locale` directly; do not
resolve dependencies during an HTTP request. All successful commands produce
one UTF-8 JSON object on stdout and exit with `0`. Operational errors produce
`{"erreur": "..."}` with a French safe message and exit with `2`. Native engine
diagnostics are suppressed so they cannot echo input fragments to application
logs. Invalid CLI syntax uses argparse's normal help and exit code `2`.

| Command | Input | Output |
| --- | --- | --- |
| `statut [--langue en\|fr]` | None | `pret`, `local`, voice alias, language and request limits |
| `installer` | None; explicit network use | `pret`, `fichiers_installes`, `local` |
| `transcrire [--langue en\|fr] /absolute/private/audio.webm` | A private audio file | `texte`, `langue`, `duree_s`, `local`, `alias` |
| `parler [--langue en\|fr] --sortie /absolute/private/new.wav` | Raw UTF-8 text through stdin | `format`, `frequence_hz`, `duree_s`, `octets`, `local`, `alias` |

Language defaults to `en` on all commands; `fr` selects the French female style. Values other than these two exact codes are rejected before inference.
Speech recognition uses the selected language explicitly, rather than a remote
or automatic translation service. Both languages use the pinned multilingual ONNX model, a fixed female style per
language, CPU inference and 24 kHz PCM output. The speech lexicon gives embedded
English technical terms their English phonemes without changing speaker mid-sentence.

The HTTP API accepts optional `langue: "en" | "fr"` on `/api/voix/parler`,
`/api/voix/transcrire` and `/api/assistant/dialogue`, and the same optional query
parameter on `/api/voix/statut`. Requests without it remain valid and now use
English. The bridge forwards the language explicitly to the subprocess and
caches readiness separately for each language for up to 60 seconds. `pret`
means the selected synthesis and all recognition paths for that language passed
hash verification (three model aliases for English, two for French);
`langues` lists supported languages, not independently verified installations.
The selected voice locale remains `en-US` or `fr-FR` in status, while inference
results use `en` or `fr`.

Assistant replies use the selected language, English by default. An explicit
user request for another reply language is respected without granting action,
tool, approval or system-prompt authority. This preference is independent of
the selected synthesis voice: select the matching voice for the best pronunciation.

Example English synthesis metadata (duration and byte count omitted):

```json
{"format":"wav","frequence_hz":24000,"local":true,"alias":"voix-feminine-en","langue":"en"}
```

The output path must not exist. Existing files and symbolic links are never
overwritten. Both audio input and output must have a private immediate parent
directory. Input files must be regular files owned by the current user with no
group/other permissions. Descriptor-based `O_NOFOLLOW` and nonblocking opening
reject symbolic links and FIFOs. Audio text is returned only as the requested
result; it is not persisted by the voice engine.

Bounds:

| Resource | Limit |
| --- | --- |
| Encoded input audio | 8,388,608 bytes |
| Decoded recording | 0.2–90 seconds |
| Audio normalization | Mono, 16 kHz, float32 |
| Accepted source complexity | At most 192 kHz and eight channels |
| Synthesis text | 1–2,000 Unicode characters |
| Synthesized speech | At most 120 seconds |
| Transcription text | At most 8,000 characters |
| Inference threads | Four CPU threads, one worker |
| Internal operation deadline | 120 seconds |

WAV, WebM/Opus and Ogg/Opus have real codec round-trip tests. Other formats
supported by the bundled decoder are not implied to have the same validation.
The decoder receives a file descriptor rather than a URL, forbids external
protocols, and counts decoded samples to reject compressed recordings that
exceed the duration limit. Voice activity detection filters silence. A short
fixed SRE vocabulary helps recognition of domain terms; it does not guarantee
transcription accuracy.

After validating the original recording, recognition adds exactly 400 ms of
zero-valued acoustic context at each boundary. Speech padding in VAD is also
explicitly 400 ms, and decoding uses a bounded ten-candidate beam. This leaves
every decoded source sample unchanged and
prevents a reproduced onset error on a short synthetic English greeting. It
does not change the public recording duration, relax the 90-second input limit,
alter model artifacts, or insert expected words into recognition prompts.

English recognition selects the dedicated `transcription-en-courte` weights only
when the decoded audio plus the two fixed context margins fits within 30 seconds:
`source_samples + 12,800 <= 480,000` at 16 kHz. The inclusive source boundary is
29.2 seconds. One additional sample selects the existing `transcription-en`
multilingual weights, even though the public duration rounds to the same 29.200.
All French recordings retain their original model and options. The returned
public alias remains `transcription-en` for both English paths. This is model
selection, with no audio splitting, changed timestamps, new lexical hint or
silently downloaded fallback. See [ADR 0021](adr/0021-reconnaissance-anglaise-dediee.md).

The API must additionally enforce authentication, CSRF protections, a bounded
upload, a bounded request queue and a single active voice operation. Use an
external subprocess timeout (130 seconds maximum) and kill its process group
on timeout or cancellation: a native library can delay Python signal handling.
Use a private temporary directory for each request and remove both uploaded and
generated audio in `finally`, including failures. Generated WAV responses must
be `no-store`. Never place speech text in process arguments, URLs or audit logs.
The speech engine deliberately creates no background service or autostart recording.
The console stores conversation text and extracted source documents in private SQLite;
raw transient microphone audio is not retained. See [conversations](CONVERSATIONS.md).

AURA uses Védric in both languages and French vous. Spoken text preserves sentence
and paragraph boundaries. The engine adds only the missing portion of a 180 ms
sentence pause, preserving existing silence and phonemes. This does not train new
voice weights. Input/output follow the operating system defaults.

The platform backup includes the console database and per-analysis checkpoints,
but excludes transient audio and downloadable voice model binaries. Model
recovery uses the pinned installation manifest above. Authentication sessions
and one-use login tickets are removed from the console copy in memory before
that copy reaches the backup disk. Each SQLite database is captured consistently;
the console and separate checkpoint files are not one atomic cross-database
snapshot while workers are running. Restore verification reports their counts
and missing checkpoints without activating the recovered state.

Show recognized text to the operator before it becomes an analysis request.
Manual message review and sending remain the default. An explicitly enabled
conversation mode may send a completed transcript to AURA automatically, play
the local reply, and then resume listening for the next turn. This is sequential
turn-taking, not simultaneous streaming or action approval. The operator must
have a visible stop control and a way to return to editable manual transcripts.
Spoken words are untrusted input. An audible “yes” is not an approval of a
diagnostic or an infrastructure operation; the existing authenticated explicit
approval control remains required. Recognition may mishear names, numbers,
negation, noise or accents, so the operator must be able to edit the transcript.

## Verification

The quick suite does not download models:

```sh
cd apps/voice
uv run --locked ruff check .
uv run --locked mypy src/voix_locale
uv run --locked pytest
uv build
```

After explicit model installation, run real speech and codec tests with network
access removed on Linux:

```sh
cd apps/voice
VOICE_TEST_REAL=1 unshare -rn uv run --locked --offline coverage run -m pytest -q
uv run --locked coverage report -m
```

An earlier working-tree run on the reference WSL2 workstation on 2026-09-27
passed **59 tests in 24.24 seconds**: 49 quick tests and ten real model tests,
with network access removed and the previously installed pinned models.
That observation did not establish repeatability: a later clean-clone check
of `a81edde3` passed 56 tests and failed three English codec round trips because
the greeting “Hello” was transcribed as “Although.” The failed synthetic WAV is
now a fixed regression fixture, with documented provenance and SHA-256 in
`apps/voice/tests/fixtures/README.md`; newly generated speech tests remain in place.

The failure reproduced with VAD disabled, and with domain hints removed. VAD
was retaining the entire original recording. Adding leading acoustic context
corrected the preserved signal; trailing silence alone did not. Successive
synthesis calls also produced different recognition results, so changing a
test assertion or merely rerunning synthesis would have hidden the issue.

Adding context with the original five-candidate decoding beam introduced a
separate regression in a synthetic confidentiality phrase: “customer data”
became “custom and data.” This candidate was rejected after comparison on eight
separately generated English/French signals. On the reference CPU backend,
a bounded ten-candidate beam preserves the greeting and confidentiality phrase, both now guarded by frozen
regression fixtures. On those same eight signals, seven retain all checked
semantic anchors, matching the baseline; a preexisting French recognition error
on “latence réseau” remains. These checks are review indicators, not an accuracy
certificate, and do not replace microphone acceptance testing.

A second, previously unused corpus of four English and four French phrases
was then compared without further parameter changes. All eight final-candidate
transcripts were identical to the baseline on the same audio signals, including
the tested negations, dates/times and quantities. Six cases matched every
automatic anchor in both versions: one unmatched case was a punctuation-only
anchor mismatch in “test, environment”; the other was a real French homophone
error, “paie” becoming “paix,” already present in the baseline. Source hashes,
model-manifest hashes and public durations matched throughout. This checks for
regression on those signals; it does not establish universal recognition
accuracy or resolve the existing French errors.

After the acoustic-context and decoding correction, a working-tree run passed
**65 tests in 37.70 seconds** with the network namespace isolated: 51 quick
tests and 14 real model tests. The real tests cover English and French synthesis
and recognition through WAV, browser WebM/Opus and Ogg/Opus, the fixed onset
regression in all three formats, the confidentiality and negation regression,
silence in both languages, private file
permissions, refusing to overwrite existing output and a real CLI subprocess.
Quick tests
cover invalid language selection before file access, shared multilingual model
artifacts, malformed media, size/duration bounds, symlinks, FIFOs,
corrupt/truncated/oversized model downloads, hash verification, atomic publication
and safe errors. They also check exact preservation of the source samples and
reported duration at both the 0.2-second and 90-second accepted boundaries.
Combined statement/branch coverage was 87%; CLI subprocess
execution is not included in that percentage. Ruff, mypy and wheel/source builds
passed and were rerun for the correction. These workstation observations are
not hosted CI evidence. Run
checks from `apps/voice`, where their configuration is defined.
The control API's separate voice and assistant suite passed **59 tests**,
including language routing, per-language caches, malformed requests, local-only
conversation, admission control, cancellation, privacy and cleanup.

Real local dialogue calls also verified AURA's AI identity, selected English
and French replies, and `actions_executees: false`. The first English request
took 60.636 seconds; the following French request took 5.702 seconds and a
repeated English request 1.047 seconds. These are short synthetic conversations;
initialization and inference latency must remain visible to the operator.
The timings do not establish the cause of the slower first request.

A reproducible load probe is available from `apps/voice`:

```sh
unshare -rn uv run --locked --offline python qualifier.py --langue en --repetitions 6 --concurrence 2
unshare -rn uv run --locked --offline python qualifier.py --langue fr --repetitions 6 --concurrence 2
```

It uses three synthetic phrases per language, private temporary audio files
and real subprocesses, reports their transcripts, and removes the audio
afterward. The English measurement completed six of six requests in 15.724
seconds with two concurrent clients. Synthesis median/max were 1.794/1.924
seconds; recognition median/max were 3.377/4.072 seconds. This includes process
startup, file hash verification, model loading and inference. These are
workstation measurements, not latency guarantees; the production API still
serializes voice operations and rejects simultaneous demand rather than queuing
unbounded audio work. Piper's high setting describes the upstream model tier,
not an independently measured listening-quality score.

The initial English load probe, before the acoustic-context correction,
produced intelligible transcripts but included recognition
errors, such as “An” becoming “and” and one “Hello” becoming “Although.” A successful
round trip means nonempty output, not perfect transcription. Review recognized
text in manual mode; conversation mode may automatically send a mistaken
transcript and can be stopped to edit it. Automatic reply playback remains optional.
The voice process synthesizes a bounded complete WAV; this implementation does
not claim streaming speech, simultaneous listening during playback or
zero-latency interruption.

The French run on 2026-09-27 completed six of six round trips in 16.839
seconds, with synthesis median/max 1.255/1.329 seconds and recognition
median/max 4.119/5.052 seconds. These French transcripts retained the phrase
words with some punctuation differences. Both languages continue to use CPU
inference, leaving the GPU for local assistant and analysis work.

The test corpus is synthetic. It does not establish a word error rate for the
operator's microphone, browser/device permission handling, accent, real alerts,
background noise or overlapping speech. Those require a recorded acceptance
corpus with consent. The UI/API integration suite separately verifies the
authenticated conversation flow, cancellation and load admission.

## CPU backend regression and qualification — 2026-09-27

After the earlier qualifications, hosted push `157077e6` failed the frozen
confidentiality fixture while its pull-request run passed. A controlled local
comparison reproduced that exact error by selecting MKL instead of oneDNN with
otherwise identical input, model and INT8 settings. Switching to float32 also
failed that fixture and was rejected. The original hosted logs did not include
CPU identity or native backend, so the local reproduction does not prove which
backend those two runners used.

With explicit oneDNN initialization, all sixteen preserved corpus transcripts
matched the earlier qualified results exactly, and both frozen regression
fixtures passed. The three previously documented anchor failures remained:
French network latency and payroll homophones, and English punctuation in
“test, environment.” The eighteen-signal replay took 37.352 seconds in total,
with a 2.080-second median and 2.305-second maximum per transcription on the
reference workstation. This includes artifact verification and model loading;
it is not a latency guarantee.

The corrected working tree passed **68 tests in 36.33 seconds**, comprising
52 quick tests and 16 real model tests with networking removed. The two added
real tests start fresh CLI processes with conflicting `CT2_USE_MKL=1` inherited
and require correct onset and confidentiality recognition. A quick test checks
the bootstrap before the native import. Overall coverage remains 87%, with
92% for the engine module; Ruff, mypy and wheel/source builds pass. These are
local measurements. New hosted runs must independently validate the correction
before release; [ADR 0020](adr/0020-backend-vocal-reproductible.md) records the
decision and early-import limitation.

## Short English recognition route — 2026-09-27

The later hosted runs of `d7030397` showed that explicit oneDNN alone was
insufficient: AMD EPYC 9V45 passed 16/16 real tests, while Intel Xeon Platinum
8573C passed 14/16 and corrupted the same frozen confidentiality phrase. The
failed attempts remain part of the evidence. No waveform, expected word or
lexical assertion was changed to make the tests pass.

Dedicated English recognition passed the two frozen onset/confidentiality
fixtures in native and AVX2 experiments. It is deliberately restricted to one
native window. Replacing the long-input path caused omissions in a fixed 89.5 s
varied recording; disabling timestamps made them worse and was rejected. The
production long-input path therefore remains the original multilingual one,
including its existing recognition limitations. No CPU ISA ceiling is imposed
in production; AVX2 is an additional regression-test configuration.

A single fixed 29.044444 s composite, made from complete network, privacy,
job-queue and date utterances with three 200 ms gaps, retained all four statements
with both models. Baseline automatic anchors were 16/16; the candidate was 14/16
because `1430`/`1515` lacked the separators required by the frozen checks. The
time values remained correct; the raw failed checks were preserved. Workstation
CLI latency was 5.196 s baseline and 10.804 s candidate; process peak RSS was
710.8 MiB and 1,595.3 MiB respectively. These measurements include verification
and model loading and are not latency guarantees.

An independent six-phrase synthetic holdout scored 4/6 with the baseline and 5/6
with the candidate, in both native and AVX2 configurations. This is not an
absence-of-regression claim: one already faulty sentence additionally changed
`runbook` into `rumble` with the candidate. Read/quote instructions were also
misrecognized. Manual transcript review remains the default; conversation mode
may forward an inaccurate transcript. Neither route grants tool approval from
speech. Real microphones, accents, noise and all possible utterances remain
outside the synthetic qualification.

The new English files add 1,530,459,085 bytes. The short-fixture experiments took
roughly 5–7 seconds per fresh call; an independent six-call process peaked near
2.5 GiB, while individual CLI probes were around 1.6 GiB. The API still permits
only one active speech operation, with the same 120 s internal/130 s external
deadlines. Earlier English browser/load figures in this guide describe the previous
recognition model and must not be presented as current route performance.

The routed working tree passed 56 quick tests in 0.93 s and all 16 real offline
tests in 66.69 s. A separate offline AVX2 replay passed all six preserved English
regressions in 37.95 s. Ruff, formatting, mypy and wheel/source builds passed;
the installer and both language statuses also verified the installed artifacts
with networking removed. These are local results, pending independent hosted
validation of the final commit and a browser replay; they do not supersede the
documented recognition failures or establish physical-microphone accuracy.

## Earlier combined release replay — 2026-09-27

The exact combined application tree `84a6fef32218` passed all 65 speech tests in
31.82 seconds from a fresh clone, with networking removed by `unshare -rn`.
Combined coverage was 87%. The separate hosted speech job downloads only the
pinned public model artifacts before removing networking for its 14 integration tests.

The real browser manual flow on the updated local service used unchanged synthetic
microphone WAVs, actual MediaRecorder, local transcription/dialogue/synthesis and
native playback. English/French STT took 2.541/2.498 seconds; dialogue 0.685/0.757;
synthesis through playback start 2.556/2.387. The reply WAVs had valid RIFF/WAVE
headers, HTTP 200, `audio/wav` and `no-store`; measured audio and Stop worked.
The transcript was explicitly reviewed and edited before Send. English still
misrecognized the opening assistant name as “Or” on this browser sample; French
recovered its sentence. This is a functional integration result, not an accuracy
certificate, physical-device test or hands-free-loop acceptance test.

Two preliminary CDP body captures returned empty bytes despite successful response
metadata. The final probe validated bytes delivered to browser fetch, then matched
the network capture and actual playback. No product change separated those attempts;
their exact capture failure cause remains unproven. All evidence, including those
failures, is in `immersive-2026-09-27/voice-browser-final/` outside Git. No operator
recording, authentication value or client data was included in the report.

## Sources and attribution

- Phonemization runtime: [Piper maintained by OHF Voice](https://github.com/OHF-Voice/piper1-gpl),
  package version `1.8.0`, GPL-3.0. The
  [upstream license](https://github.com/OHF-Voice/piper1-gpl/blob/main/COPYING)
  applies to redistribution of that component; preserve the relevant notices
  and corresponding source obligations when distributing a runtime bundle.
- Current synthesis: [Kokoro-82M v1.0](https://huggingface.co/hexgrad/Kokoro-82M),
  hexgrad and contributors, Apache-2.0. The manifest pins the
  [ONNX conversion](https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX)
  by full immutable revision, byte size and SHA-256 in `modeles.json`. English uses the
  female `af_heart` style; French uses `ff_siwis`. One shared 326 MB model and
  two small style tensors replace the previous two synthesis models. No torch
  pickle, remote code or online inference is loaded.
- French training attribution remains [SIWIS](https://datashare.ed.ac.uk/handle/10283/2353),
  Yamagishi, Honnet, Garner and Lazaridis (2017), University of Edinburgh,
  DOI `10.7488/ds/1705`, CC-BY-4.0. Retain this attribution alongside the model
  notices. Generated speech is not a recording or endorsement by the speaker.
- The earlier Piper LJSpeech/SIWIS synthesis results in this document are historical
  qualification evidence, not measurements of the current multilingual engine.
- Speech recognition: [faster-whisper](https://github.com/SYSTRAN/faster-whisper),
  package version `1.2.1`, and its
  [small multilingual converted model](https://huggingface.co/Systran/faster-whisper-small/blob/536b0662742c02347bc0e980a01041f333bce120/README.md),
  MIT license. Short English recognition additionally uses the
  [pinned English-only converted model](https://huggingface.co/Systran/faster-whisper-medium.en/blob/a29b04bd15381511a9af671baec01072039215e3/README.md),
  also MIT. Its five artifacts total 1,530,459,085 bytes; each immutable revision,
  size and SHA-256 is in the manifest. Both model cards are installed with their
  weights.
- [Piper Python API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md)
  and the faster-whisper source document the local inference interfaces used.

The dependency lock includes the exact runtime versions and artifact hashes;
the model manifest pins immutable revisions and file hashes independently.


## Conversational speech and background music — 2026-09-27

AURA addresses the operator as **Védric**, uses **vous** in French and keeps the
reply conversational: short phrases, direct answers and no repeated introductions.
This is prompt/prosody engineering, not model-weight fine-tuning. The fixed welcome
starts “Bonjour Védric, contente de vous retrouver”, with no artificial pause
between the greeting and the name. Written answers retain correct technical spelling.

The trusted lexicon covers GitHub, Enterprise, Kubernetes, Terraform, DevOps,
SRE, MCP, CI/CD and other common engineering terms. Raw phonetic markup from user
text is neutralized. Words remain inside a continuous sentence with the same voice;
long phoneme sequences split at word boundaries within the model's context limit.
Unsupported phonemes fail visibly instead of silently losing part of a sentence.

The multilingual qualification passed 72 unit tests and 18 real model tests,
including both browser recording codecs, frozen onset/confidentiality regressions,
French greetings and mixed French/English technical terms. In one synthetic
comparison, French synthesis took 1.486 seconds for 10.4 seconds of speech; English
1.185 seconds for 9.05 seconds. These are individual CPU observations, not latency
SLOs. Recognition of generated speech is an intelligibility check, not an independent
human listening score. Rare names, accents, noisy microphones and other machines
still need listening/recognition acceptance tests. AURA does not claim human identity.

Enable **Play ambient music** from the header, or **Settings → Voice preferences**.
The local original track **Orbital Drift** lasts 96 seconds and loops. Its score and
asset are CC0-1.0; see the [audio notice](../apps/console/public/audio/NOTICE.md).
Default level is 12%, capped at 22%. AURA and guide videos reduce that level to 8%
of the selected background level; microphone acquisition/recording mutes the music.
The return fades over 1.4 seconds. Hiding the tab pauses playback; Escape disables
music. The preference persists in this browser. Browsers can require an explicit
click after reload; the visible play control resumes it. No third-party music service,
subscription, tracker or network stream is involved.

Playwright verifies real MP3/WAV playback, welcome attenuation, recording silence
and stop persistence in desktop and mobile Chromium. Physical speaker levels and
Safari/Firefox playback are not certified by Chromium emulation.


## Browser recovery and narrated guides (0.4.1 console / 0.3.1 voice)

Language choices are **English voice** and **French voice**; the internal aliases
remain unchanged. The desktop AURA deck runs horizontally, with an optional
heartbeat accent. Reduced motion, Pause animations, offscreen scenes and hidden
tabs suspend decorative activity; measured input still drives signal feedback.

The browser microphone analyser now feeds a zero-gain destination to keep the
audio graph active without audible microphone feedback. The AudioContext activated
by the initial click is reused between hands-free turns, then closed on completion,
error or cancellation. Native output follows the system default without `setSinkId`.
**Check microphone & sound** captures at most eight seconds for local replay, with
no API upload. It releases tracks and object URLs on cancellation/unmount and
handles denied permission or blocked playback explicitly. Physical device privacy
and OS/browser volume cannot be changed by the web application.

The phonemizer is initialized once per process and serialized across voice switches.
eSpeak owns native global state: repeatedly initializing it during multilingual
synthesis caused native warnings and a stalled guide build. A bounded subprocess
regression alternates French and English from concurrent callers and requires
stable phonemes without eSpeak corruption diagnostics. Unrelated ONNX hardware
discovery warnings on hosted runners do not fail this phonemization assertion.

Six narrated guides now use H.264 video and AAC audio in MP4. The earlier WebMs
contained only video, so moving playback did not prove the presence of sound.
Automated checks now decode each audio track, verify nonzero RMS and asset hashes,
and check actual browser audio decoding alongside video progression. Narration
uses only `scripts/guide-script.json`, generated locally under a 130-second limit
per caption. To regenerate with the disposable preview on 8789:

```sh
uv run --locked --project apps/voice python apps/console/scripts/narrate-guides.py prepare /absolute/private/guide-evidence
cd apps/console
node scripts/record-guides.mjs /absolute/private/session.json /absolute/private/guide-evidence
cd ../..
uv run --locked --project apps/voice python apps/console/scripts/narrate-guides.py mux /absolute/private/guide-evidence
```

The session file contains only the disposable preview API key; it is never copied
into public assets. Keep the intermediate WAV/WebM directory private and publish
only reviewed MP4s, posters, captions and provenance. Audio licensing is recorded
in `apps/console/public/audio/NOTICE.md`.

Browser behavior follows [MDN Web Audio activation guidance](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API/Best_practices)
and [autoplay handling](https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Autoplay).
These describe browser constraints; passing automated tests does not verify a
physical Windows microphone or speaker.
