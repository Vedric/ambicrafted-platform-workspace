# Narrated user guides

The Guide page contains six workflows in English and French. Each has four
chapters, optional captions, a complete transcript and practical next steps:

| Workflow                  | Demonstrated behavior                                              |
| ------------------------- | ------------------------------------------------------------------ |
| First steps               | Welcome, readiness checks, mission selection and source runbooks   |
| Talk with AURA            | Microphone check, a conversation turn and conversation history     |
| Investigate with evidence | Synthetic alert, cited proposal, explicit rejection and history    |
| Documents and memory      | Diagram, report, export controls and an unsaved memory draft       |
| Backup and recovery       | Backup and restore confirmations, cancellation and readiness       |
| Monitor the platform      | Monitoring freshness, service health and architecture dependencies |

These are recordings of the real disposable application, with deterministic
synthetic inference/transcription responses. They teach the controls and their
limits; they do not demonstrate model accuracy, a physical microphone, a real
backup operation or actual infrastructure traffic. Neither the memory draft nor
the backup confirmations are submitted in these recordings. The local narration
is generated separately with the pinned voice models. No customer data is used.

## Playback and accessibility

The videos are 1920 × 1080 H.264 with a separately decoded AAC narration track.
Native browser controls support pause, seek, volume, speed and fullscreen. Videos
do not autoplay and pause when the page becomes hidden. Captions are ordinary
WebVTT tracks, not burned into the picture. The **Captions** button is keyboard
accessible and remembers its choice across lessons and reloads when local storage
is available. Native caption changes update the same preference. The transcript
remains available when captions or the video cannot load. Four chapter buttons
show translated titles and timecodes from the actual recording. They seek without
starting a paused video, including before its first playback, and preserve the
caption preference. Video data loads on demand; no autoplay is introduced.

The build imports only `src/guide-chapters.json`, a small mapping of chapter
offsets generated alongside the media. The full provenance and audio metadata
are not imported into the guide bundle. Asset tests compare every offset with
the corresponding recorded cue.

Caption phrases are limited to two lines of 44 characters. Timing is distributed
within each spoken chapter by phrase length; this is approximate alignment, not
word-level forced alignment. Native capture frame rate and encoded frame rate
are recorded separately in `public/guides/provenance.json`; resampling a capture
to 30 fps does not create new native animation frames. Audio and video packets
are interleaved by decoding timestamp, with the MP4 index at the beginning
(`faststart`), so progressive playback does not wait for most of the video before
receiving its first audio packet. The asset tests verify physical packet order
in addition to complete audio decoding and narration in every chapter.

## Rebuild in a disposable environment

Use the pinned Node and Python environments from the repository. First install
locked dependencies and verified public voice models according to [VOICE.md](VOICE.md).
Prepare the bilingual narration outside the checkout:

```sh
uv sync --locked --project apps/voice
unshare --user --map-root-user --net apps/voice/.venv/bin/python \
  apps/console/scripts/narrate-guides.py prepare /absolute/private/guide-build
```

Start `apps/console/tests/server.py` with the same disposable settings as the
Playwright configuration: temporary state/project, a synthetic API key and
password, loopback port `8789`, and the built console. Never point this server at
production state. Put its temporary key in a private mode-0600 JSON file with a
`key` field; do not put credentials in command arguments or commit that file.
From `apps/console`, record all twelve clips:

```sh
node scripts/record-guides.mjs /absolute/private/session.json \
  /absolute/private/guide-build
```

The optional final argument selects one existing recording to replace, for
example `documents-fr`, or one language. It requires the existing private
`recordings.json`; preserve failures and their evidence before retrying. Build
the console before capturing and keep that build fixed throughout the recording.
Then encode and validate all clips:

```sh
apps/voice/.venv/bin/python apps/console/scripts/narrate-guides.py mux \
  /absolute/private/guide-build
uv run --locked --project apps/voice pytest apps/voice/tests/test_guides.py -q
```

Encoding verifies the source hashes, twelve unique bilingual clips, four
chapters, native 1080p frames, finite audible narration and a bounded duration.
Each output replaces its destination only after successful encoding and decode
validation. The manifest identifies media and caption hashes, original capture
hashes, frame rates, narration and chapter timing. A failed batch is not a
publishable guide set: run the complete asset tests before rebuilding the UI.
The browser suite `e2e-guides.spec.ts` additionally exercises real media playback,
caption persistence, keyboard operation and transcript fallback. A real Web Audio
`OfflineAudioContext` also decodes and measures the MP4 narration in each browser
engine, without depending on physical speakers. This proves audio decoding, not
physical speaker output.

## English pronunciation compatibility

The pinned Kokoro vocabulary does not contain U+0329, the IPA syllabic diacritic,
although the English phonemizer can produce `n̩` and `l̩` in common words. The
English synthesis adapter approximates just these two syllabic consonants with
`ən` and `əl`, preserving a vocalic nucleus supported by the model. This is an
implementation compromise for this vocabulary, not a universal phonetic
conversion. French is unchanged; unsupported other diacritics remain a visible
error rather than being silently removed.

The [IPA chart](https://www.internationalphoneticassociation.org/content/chart)
and [eSpeak NG phoneme documentation](https://github.com/espeak-ng/espeak-ng/blob/master/docs/phonemes.md)
identify the syllabic notation. The exact vocabulary source and SHA256 are
pinned in `apps/voice/src/voix_locale/modeles.json`. Real offline synthesis and
transcription checks cover the English words “written”, “button” and “table”
and a French control sentence, alongside the existing voice integration suite.
These automated checks do not substitute for listening on the operator's own
speakers and microphone.

## Practise a complete engineering task

Use a new conversation for each exercise. These are realistic **fictional**
situations, not customer incidents or claims about the machine running the
platform. AURA can draft the review from supplied evidence; it does not inspect
an external cluster merely because the request mentions Kubernetes.

1. Check **Readiness**, then choose the relevant mission. For an incident,
   prepare the applicable runbooks before starting a supervised analysis.
2. Supply observations, timestamps, scope and explicit unknowns. In AURA, attach
   the relevant local files and select them for the turn. Choose **Report** for
   a written review or **Diagram** for architecture. Start with a small, explicit
   request before combining several documents.
3. Compare the draft against the original inputs. Check numbers, units, time
   windows, identities, source excerpts and words such as “approved”, “tested”
   or “absent”. A successful consistency check is not independent evidence.
4. Ask for a revision when the draft changes a supplied fact. If validation
   refuses the document, simplify or clarify the inputs; do not reinterpret the
   refusal as a completed report. Inspect the history before retrying.
5. Export only the reviewed result. A memory note requires a separate scope and
   explicit save. Use [the complete client workflow](CLIENT-WORKFLOW.md) for
   mission separation, approval, handover and recovery.

| Practice | Supply these facts | What a useful review should distinguish |
| --- | --- | --- |
| SRE incident | HTTP 504 on 18% of requests since 14:30 UTC; direct upstream response 120 ms; gateway timeout 5 s; configuration changed at 14:20; no upstream logs | Symptoms versus cause; a nearby change versus proven causality; the missing common-window logs and latency measurements |
| DevOps release | A canary received 20,000 requests over 30 minutes; errors 0.1% in both cohorts; p95 140 ms versus 135 ms; acceptance thresholds and owner unspecified | Observed difference versus acceptance; comparable cohorts and time windows; the human decision and rollback evidence still needed |
| DevSecOps review | Three of eight images scanned; five builds failed; the scanned images have no HIGH findings | A scanned result versus an unknown result; exact image digests, scanner database date and required reruns; no “zero vulnerabilities” claim for unscanned images |
| Platform engineering | NetworkPolicy allows ingress from observability; that path succeeds; no forbidden-path test or CNI evidence supplied | Expected allowed traffic versus enforcement; ingress versus egress; required positive and negative tests with the intended identities |
| Cloud architecture | Browser calls an API over HTTPS; API queries PostgreSQL; authentication, database transport and backup design unspecified | Three supplied components and their directions; unknown controls versus proposed controls; no invented deployment, replica count or trust boundary |
| Recovery planning | Backups every 24 hours; proposed RPO one hour; proposed RTO 15 minutes; no restore exercise; recovery key only on the same workstation | The RPO mismatch, unmeasured RTO and shared failure domain; a non-empty isolated restore and independently held recovery material |

For a diagram, inspect the full outline and source markers before exporting;
zoom and expand the workspace when labels are small. For a report, confirm that
unknown items remain unknown rather than becoming failed controls. Repeat a
small exercise through the [CLI document workflow](AURA-ARTIFACTS.md#cli): the
same saved conversation and export authorization apply. Keep private request
text in an operator-owned file or stdin, not shell arguments.
