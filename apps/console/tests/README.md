# Browser qualification

Run from `apps/console`, after installing the locked API environment:

```sh
npm ci
npm run build
npx tsc --project tests/tsconfig.json --pretty false
npx playwright install --with-deps chromium firefox webkit
npm test
npm run test:e2e
```

`playwright.config.ts` starts `tests/server.py` on **127.0.0.1:8789** and refuses
to reuse an existing server. It uses `~/.local/bin/uv` when present, otherwise
`uv` on `PATH`; set `PLATFORM_TEST_UV` to override the executable path in CI.
Password and API key are generated per run and passed only to the disposable
test processes. The server never reads the workstation `.env` or its databases.
Its corpus and SQLite state live in a temporary private directory and are
removed after shutdown. The source application contains no test bypass flag.

The browser suite runs the production frontend build against the **real HTTP
API**, session cookies, CSRF boundary, SQLite repository, runbook editor and SSE.
It covers desktop Chromium and a mobile Chromium viewport, password/ticket
authentication, approval/refusal/cancellation, export/deletion, editing conflicts,
search, operations, keyboard navigation, motion preferences, session expiration,
offline states and retryable submission. Axe checks WCAG A/AA rules without
excluding contrast findings. Uncaught browser exceptions fail the tests.

The inference engine, assistant dialogue, service-health probes and semantic-search answers are
deterministic replacements defined only in `server.py`. An operational job here
does not run Docker, create a real backup or invoke a model. Explicit route
failures exercise client recovery. These tests therefore prove UI/API wiring and
workflow behavior; they do not prove diagnostic correctness, speech quality,
GPU performance or real backup recovery. Those need separate workstation
acceptance. Firefox and WebKit run the additional critical journeys described
below; WebKit on Linux is not an acceptance test on a physical Safari/iOS device.

Vitest unit tests cover fetch/CSRF/error handling, diagnostic-shape validation,
public authentication states and inert rendering of hostile Markdown. Browser
reports, traces and failure screenshots are local test artifacts. Do not commit
them or reuse real incident content in these fixtures.


Browser/media recovery regressions cover password sign-in from `/welcome` in
English and French, authenticated password setup after CLI entry, an eight-second
local microphone diagnostic without API upload, real encoded sample replay,
narrated H.264/AAC playback for every guide, and retry after a failed media load.
`apps/voice/tests/test_guides.py` additionally checks audio codecs, RMS, hashes
and caption alignment. Browser microphones are synthetic test signals; physical
hardware permission and listening acceptance remain an operator check.

## Critical journeys across browser engines

`e2e-critical-paths.spec.ts` runs in Chromium desktop/mobile and separate Firefox
and WebKit projects. It covers password entry and logout, actual cookie/CSRF
boundaries, English/French settings, light theme and responsive layout, explicit
human approval, JSON download, rejection, cancellation, streamed dialogue, CSV
upload, explicit source selection, persistent history and deletion. Every
uncaught browser error fails the journey. Motion-preference and welcome/AURA
animation checks also run on Firefox and WebKit; the full media/GPU suite is
not claimed on every engine.

```sh
npx playwright test --project desktop-firefox-critical --project desktop-webkit-critical
```

A missing browser executable or system dependency is a failed setup, never a
skipped success. Use the Playwright CLI from the repository lock, not an
unpinned system install. CI installs all three engines. Physical microphone,
speaker routing, autoplay policy and perceived voice quality remain a separate
operator acceptance on the actual supported device.

## Saved documents and guide lessons

`e2e-artifacts.spec.ts` exercises the real conversation database/export routes,
with deterministic generation only. It checks graph persistence, source-preserving
SVG/PNG/JSON downloads, both orientations on a 24-node/40-edge grouped graph,
light/dark layouts, hostile markup refusal, selected-document print isolation,
and editable memory drafts without automatic writes. Firefox and WebKit run
these document journeys in addition to desktop/mobile Chromium. The DOM checks
measure actual rendered text bounds; they are not image-quality certification.

Unit tests cover malformed schemas, Unicode boundaries, stalled layout workers,
font readiness, abort handling, stale sessions, bounded authenticated exports
and oversized raster refusal. `e2e-guides.spec.ts` covers caption preferences,
transcripts and failure signaling. See [guide production](../../../docs/GUIDES.md)
for the separate native video, narration and reproduction checks.
