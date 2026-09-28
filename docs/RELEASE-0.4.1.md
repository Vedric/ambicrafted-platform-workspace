# Browser access and media recovery — 28 September 2026

Console 0.4.1; speech runtime 0.3.1; control API remains 0.4.0.
This patch addresses reported regressions in the private local workspace. It
retains the production boundaries in [the 0.4 assessment](RELEASE-0.4.0.md).

## User-visible corrections

- Password login from `/welcome` now enters the workspace immediately, in either
  language. Authenticated sessions without a configured password show a link to
  **Settings → Console password**, so direct browser entry remains available
  after the current session expires. The CLI's one-use tickets remain supported.
- AURA uses a horizontal desktop control area, a restrained heartbeat accent,
  responsive cards and plain English/French voice choices. Scroll entrances use
  short fades: translating observed cards at the viewport boundary caused
  repeated intersection changes and unstable buttons on mobile.
- Microphone analysis has an inaudible connected output, and hands-free turns
  reuse the AudioContext activated by the initial gesture. End, Escape, hidden
  tabs, navigation and errors release capture. Default audio output no longer
  depends on optional speaker selection.
- **Check microphone & sound** records at most eight seconds and replays locally.
  Permission denial, silence and failed playback produce actionable feedback.
  Diagnostic audio is not uploaded or retained in conversation history.
- All six guides now contain H.264 video, audible AAC narration and aligned
  English/French captions. The old WebMs had no audio track. Native volume,
  seeking, retry and direct video access remain available. Early load failures
  are detected even before React attaches media event listeners.
- The native speech phonemizer is initialized once per process and serialized
  across language switches. This removes the repeated native initialization
  observed during guide generation. Narration generation also has a per-caption
  process deadline.

## Verification

The targeted qualification includes 222 UI unit tests, 79 speech/asset tests and
18 real-model speech tests under network isolation. Six guide assets are checked
for exact hashes, expected codecs, decoded audio energy and caption alignment.
The browser suite covers 60 desktop/mobile Chromium scenarios including login,
CLI ticket entry, session expiration, microphone capture/replay, hands-free turns,
video retry and navigation, both themes, reduced motion and accessibility scans.

An additional browser run against the real local API used synthetic WAV input
through Chromium's actual MediaRecorder, then local recognition, a generated
reply and native WAV playback. English recognition/dialogue/playback-start took
7.156 / 0.859 / 1.339 seconds in one run; French took 2.857 / 0.847 / 1.730 seconds.
These are individual observations, not latency guarantees or listening scores.
Only the loopback origin was contacted and no browser page exception occurred.
Synthetic conversations created by the checks are removed afterward.

The eight viewport/theme combinations (390, 768, 1024 and 1440 logical pixels,
light and dark) were checked for overflow and automated accessibility violations.
Full release qualification must use the exact committed revision and a clean
checkout; GitHub checks and the release tag identify that revision.

## First use after updating

Open `http://127.0.0.1:8787/welcome`. If no password is configured and your old
session has expired, run `./plateforme ouvrir` once, then set a password in
Settings. Use the same hostname consistently: localhost and 127.0.0.1 have
separate browser permissions and cookies. No password is set on your behalf.

In AURA, allow microphone access and use **Check microphone & sound** to verify
your actual device. **Record** captures a draft; finish, review and send it.
**Start conversation** explicitly enables successive voice turns. Browser
permission, hardware mute and OS/tab volume still require operator control.

Physical Windows microphones/speakers and Safari/Firefox were not certified by
Chromium tests. Existing infrastructure advisories, commercial tenancy, hardware
qualification and other production conditions in the 0.4 report remain open.
No finite test suite establishes zero defects or zero vulnerabilities.
