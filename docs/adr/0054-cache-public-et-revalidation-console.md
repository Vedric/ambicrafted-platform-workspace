# ADR 0054 — Cache versioned assets; revalidate the console entry

Date: 2026-10-24

Status: Implemented; release and installed-host acceptance recorded separately.

## Context

The console serves Vite's content-versioned modules, stylesheets and fonts from
the same local origin as its private API. File responses previously had no
explicit cache policy. Direct `/index.html` requests also bypassed the entry
route's `no-cache` header. A missing module or video fell through to the SPA's
HTML response, disguising a missing file as HTTP200.

## Decision

Use the existing Starlette static-file implementation for asynchronous file
lookup, conditional requests, HEAD and byte ranges. Give only the pinned build's
eight-character-hash JS, CSS and WOFF2 files under `/assets/` a one-year immutable
public cache policy. Other files, including HTML, named audio and videos, must
revalidate. Preserve conditional HTTP304 responses and video seeking.

Missing assets return HTTP404 with `no-store`; they never receive the SPA entry.
Extensionless application routes retain the HTML fallback. An absent entry
reports HTTP503. Existing API authentication, CSRF, security headers and
`no-store` responses remain independent of the public-file handler.

The UI query cache is still cleared on logout/session expiry. Conversation
history, generated replies and microphone recordings are not added to an HTTP
cache, service worker or shared semantic cache. Local model retention remains
bounded by the runtime and the existing 24-hour preparation request.

## Alternatives rejected

- Cache every response: risks stale private state and unauthorized reuse.
- Mark unversioned videos or `index.html` immutable: can pin old content across
  a deployment and break newly referenced modules.
- Add Redis or a service worker for this single-operator workload: no measured
  requirement justifies another consistency or lifecycle boundary.
- Automatically reload on a missing module: could discard an unsaved draft.
  The existing recovery screen lets the operator choose when to reload.

## Consequences and verification

Repeat navigation can reuse the public build without transferring it again.
Changing build contents must produce new versioned filenames. Older tabs can
still reference removed chunks after deployment; revalidating HTML enables
recovery on reload, but does not retain every historical build indefinitely.
Local cache hits are not a network, inference or multi-user scalability claim.

HTTP integration tests cover conditional requests, deployment invalidation,
private responses, missing files, byte ranges and an external symlink refusal.
Playwright records actual transferred bytes on first and second navigations,
with a fresh browser context. It also checks the public/private cache boundary.
The dated qualification records exact results, environments and failures.

References: [Starlette static files](https://www.starlette.io/staticfiles/),
[file responses](https://www.starlette.io/responses/#fileresponse), and
[Vite deployment/load-error handling](https://vite.dev/guide/build#load-error-handling).
