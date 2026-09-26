# Browser qualification

Run from `apps/console`, after installing the locked API environment:

```sh
npm ci
npm run build
npx tsc --project tests/tsconfig.json --pretty false
npx playwright install chromium
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
GPU performance, real backup recovery or behavior in Safari/Firefox. Those need
separate workstation acceptance or additional browser projects.

Vitest unit tests cover fetch/CSRF/error handling, diagnostic-shape validation,
public authentication states and inert rendering of hostile Markdown. Browser
reports, traces and failure screenshots are local test artifacts. Do not commit
them or reuse real incident content in these fixtures.
