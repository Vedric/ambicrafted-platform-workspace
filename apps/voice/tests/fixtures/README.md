# Synthetic speech regression fixture

`english-onset.wav` contains only the following synthetic text:

> Hello, I am your local assistant. The platform protects your data. Would you like to analyze an alert?

It was generated locally on 2026-09-27 by the unmodified `voix-feminine-en`
alias from commit `a81edde3`, using the exact artifacts in
`src/voix_locale/modeles.json`. The voice weights and source dataset are public
domain; attribution and upstream sources are documented in `docs/VOICE.md`.
No microphone recording, operator text or customer data is included.

The original waveform is deliberately frozen: synthesis includes random noise,
so regenerating it would not reproduce the same recognition regression. On the
original runtime this recording transcribed the first word as “Although” in WAV,
WebM/Opus and Ogg/Opus. Its speech region began at sample zero; disabling VAD did
not correct the error. A short leading quiet context restores the expected
greeting for this recording. The lexical assertions remain the
same as those for newly synthesized speech; model names, hints and text are not
changed to force recognition of the expected greeting.

- WAV: mono signed 16-bit PCM, 22,050 Hz, 263,724 bytes.
- SHA-256: `4617ec10d8aa913213673ee15f6fbca882b0c754a968d9610bec29252e2f8729`.
- Generated media only: the test copies it into a private directory with mode
  `600` before calling the engine, just like browser uploads.

`english-confidentiality.wav` was generated separately from the same commit and
pinned voice as part of an independent evaluation corpus. Its synthetic text is:

> Keep these logs on this local workstation. Do not send customer data to an external service.

Adding quiet context with the original five-candidate decoding beam corrected
the greeting above but changed “customer data” into “custom and data” here.
The final ten-candidate beam preserves both phrases. This second fixture guards
that observed regression and checks that the prohibition and local-only scope
remain intact. It is not a microphone or population-level accuracy benchmark.

- WAV: mono signed 16-bit PCM, 22,050 Hz, 266,284 bytes.
- SHA-256: `ef59eaaa990183185e48cb95cfab730898a1c57943e1e6821f3acbe7f5002c85`.
