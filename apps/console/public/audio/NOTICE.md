# AURA welcome audio provenance

These English and French WAVs were synthesized locally for this platform, using
the immutable artifacts recorded in `apps/voice/src/voix_locale/modeles.json`.
`welcome-provenance.json` records their transcripts, hashes and durations.

- Synthesis: [Kokoro-82M v1.0](https://huggingface.co/hexgrad/Kokoro-82M),
  hexgrad and contributors, Apache-2.0; pinned ONNX conversion by onnx-community.
  The female styles are `af_heart` (English) and `ff_siwis` (French). The shared
  multilingual model generates both native sentences and embedded English terms.
- French training attribution: SIWIS, Yamagishi, Honnet, Garner and Lazaridis
  (2017), *The SIWIS French Speech Synthesis Database*, University of Edinburgh,
  DOI 10.7488/ds/1705. [Dataset](https://datashare.ed.ac.uk/handle/10283/2353),
  [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/).
- Phonemization uses the pinned Piper/eSpeak component; its GPL-3.0 licensing is
  separate from the speech model. See [VOICE.md](../../../../docs/VOICE.md).

The audio is newly synthesized speech, not an original recording. No original
speaker is claimed to endorse this platform. The interface identifies AURA as AI.

## Original ambient score: Orbital Drift

`orbital-drift.mp3` and its procedural musical score are dedicated to the public
domain under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/).
This dedication applies only to this instrumental, not to the voice models or
other repository assets. No third-party samples, recordings, soundtrack melody,
or composition were used. The score uses synthesized sine pads and sparse bells.

Reproduce it with the pinned voice environment:

```sh
uv run --locked --project apps/voice python apps/console/scripts/generate-ambient.py
```

`ambient-provenance.json` records the asset hash, duration and decoded signal levels.
Playback starts with an explicit choice; browser autoplay policy can require a new
click after reload. The score is deliberately limited to a low background level.


## Narrated user guides

The English/French narration in `../guides/*.mp4` is generated with the same
pinned local speech runtime and voice styles as the welcome assets above.
`../guides/provenance.json` records the caption text, audio/video codecs,
durations and SHA-256 hashes. The recordings show synthetic UI examples.
No microphone recording, customer data or third-party soundtrack is included.

`speaker-check.wav` is an original one-second two-tone output test generated mathematically (440/660 Hz, 24 kHz PCM). No samples or third-party assets; dedicated under CC0. It plays only on an explicit Test speakers action.
