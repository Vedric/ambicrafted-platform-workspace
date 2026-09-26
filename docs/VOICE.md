# Private French voice

The console uses two local speech engines in a separate Python 3.13 process: a
French female synthetic voice and French speech recognition. Speech processing
uses CPU inference with four threads per process, leaving the GPU available to
the SRE agent. The speech engine neither decides on actions nor executes tools.
The control API owns authentication, concurrency, conversation and approval.

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
```

Installation downloads approximately 550 MB of public model files. It requires
network access only for this explicit step. The package's
`src/voix_locale/modeles.json` records immutable upstream revisions, exact byte
counts, SHA-256 checksums, aliases and attribution. Downloads are written to
private temporary files and published atomically after verification. Concurrent
installation is rejected. Repeating installation reuses valid files and repairs
corrupt ones.

Models are stored outside Git in
`~/.local/state/ambicrafted/voice/{synthese,transcription}`. Set `VOICE_STATE_DIR`
to an absolute private directory to override the location. Directories must be
owned by the current user, mode `700`, without symbolic links. Model files use
mode `600`. New intermediate state directories also use `700`. Every inference
verifies model file sizes and hashes before loading them. Runtime model names in
code are only the aliases `voix-feminine-fr` and `transcription-fr`; the model
manifest is the source configuration.

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
| `statut` | None | `pret`, `local`, voice alias, language and request limits |
| `installer` | None; explicit network use | `pret`, `fichiers_installes`, `local` |
| `transcrire /absolute/private/audio.webm` | A private audio file | `texte`, `langue`, `duree_s`, `local`, `alias` |
| `parler --sortie /absolute/private/new.wav` | Raw UTF-8 text through stdin | `format`, `frequence_hz`, `duree_s`, `octets`, `local`, `alias` |

Example synthesis result:

```json
{"format":"wav","frequence_hz":22050,"duree_s":6.49,"octets":286252,"local":true,"alias":"voix-feminine-fr"}
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

The API must additionally enforce authentication, CSRF protections, a bounded
upload, a bounded request queue and a single active voice operation. Use an
external subprocess timeout (130 seconds maximum) and kill its process group
on timeout or cancellation: a native library can delay Python signal handling.
Use a private temporary directory for each request and remove both uploaded and
generated audio in `finally`, including failures. Generated WAV responses must
be `no-store`. Never place speech text in process arguments, URLs or audit logs.
The speech engine deliberately creates no background service, history or
autostart recording.

The platform backup includes the console database and per-analysis checkpoints,
but excludes transient audio and downloadable voice model binaries. Model
recovery uses the pinned installation manifest above. Authentication sessions
and one-use login tickets are removed from the console copy in memory before
that copy reaches the backup disk. Each SQLite database is captured consistently;
the console and separate checkpoint files are not one atomic cross-database
snapshot while workers are running. Restore verification reports their counts
and missing checkpoints without activating the recovered state.

Show recognized text to the operator before it becomes an analysis request.
Spoken words are untrusted input. An audible “yes” is not an approval of a
diagnostic or an infrastructure operation; the existing authenticated explicit
approval control remains required. Recognition may mishear names, numbers,
negation, noise or accents, so the operator must be able to edit the transcript.

## Verification

The quick suite does not download models:

```sh
uv run --project apps/voice --locked ruff check apps/voice
uv run --project apps/voice --locked mypy apps/voice/src/voix_locale
uv run --project apps/voice --locked pytest apps/voice/tests
uv build --project apps/voice
```

After explicit model installation, run real speech and codec tests with network
access removed on Linux:

```sh
cd apps/voice
VOICE_TEST_REAL=1 unshare -rn uv run --locked --offline coverage run -m pytest -q
uv run --locked coverage report -m
```

On the reference WSL2 workstation on 2026-09-26, all **43 tests** passed in
12.78 seconds with the network namespace isolated: 37 quick tests plus six real
model tests. The real tests cover synthesis, recognition, WAV, browser
WebM/Opus and Ogg/Opus, silence, private file permissions, refusing to overwrite
existing output and a real CLI subprocess. Quick tests cover malformed inputs,
size/duration bounds, symlinks, FIFOs, corrupt/truncated/oversized model
downloads, hash verification, atomic publication and safe errors. Combined
statement/branch coverage was 86%; subprocess execution is not included in
that percentage. Ruff, mypy and wheel/source builds also passed.

A separate initial isolated CLI measurement synthesized 6.49 seconds of French
speech in 1.13 seconds, then transcribed it in 3.64 seconds; both subprocesses
had empty stderr. These are workstation measurements, not latency guarantees.
The dependency audit of the 26 locked runtime dependencies reported no known
vulnerabilities on the same date. Audit again during delivery; an absence of
known advisories does not assess every native decoder behavior.

A reproducible load probe is available as
`unshare -rn uv run --locked --offline python qualifier.py --repetitions 6 --concurrence 2`
from `apps/voice`. It uses three synthetic French phrases, private temporary
audio files and real subprocesses, reports their transcripts, and removes the
audio afterward. The measured run completed six of six round trips in 13.252
seconds with two concurrent clients. Synthesis median/max were 1.059/1.073
seconds; recognition median/max were 3.393/3.445 seconds. The transcripts
preserved the words of these short synthetic phrases with punctuation
differences. This is a bounded component load probe; the production API still
serializes voice operations and must test its own admission control.

The test corpus is synthetic. It does not establish a word error rate for the
operator's microphone, browser/device permission handling, accent, real alerts,
background noise or overlapping speech. Those require a recorded acceptance
corpus with consent. The UI/API integration suite separately verifies the
authenticated conversation flow, cancellation and load admission.

## Sources and attribution

- TTS runtime: [Piper maintained by OHF Voice](https://github.com/OHF-Voice/piper1-gpl),
  package version `1.8.0`, GPL-3.0. The
  [upstream license](https://github.com/OHF-Voice/piper1-gpl/blob/main/COPYING)
  applies to redistribution of that component; preserve the relevant notices
  and corresponding source obligations when distributing a runtime bundle.
- French voice: the pinned Piper SIWIS medium model, trained with the
  [SIWIS French Speech Synthesis Database](https://datashare.ed.ac.uk/handle/10283/2353),
  by Junichi Yamagishi, Pierre-Edouard Honnet, Philip Garner and Alexandros
  Lazaridis, University of Edinburgh, 2017, DOI `10.7488/ds/1705`. Its
  [model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/fr/fr_FR/siwis/medium/MODEL_CARD)
  identifies the dataset license as CC-BY 4.0. The model card is installed with
  the voice, alongside this attribution.
- Speech recognition: [faster-whisper](https://github.com/SYSTRAN/faster-whisper),
  package version `1.2.1`, and its
  [small multilingual converted model](https://huggingface.co/Systran/faster-whisper-small/blob/536b0662742c02347bc0e980a01041f333bce120/README.md),
  MIT license. The pinned model card is installed with its weights.
- [Piper Python API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md)
  and the faster-whisper source document the local inference interfaces used.

The dependency lock includes the exact runtime versions and artifact hashes;
the model manifest pins immutable revisions and file hashes independently.
