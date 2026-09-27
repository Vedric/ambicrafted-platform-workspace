# 0024 — A cached public technology watch

Date: 2026-09-27. Status: implementation qualified for the local private scope.

## Context

AURA should follow its personal welcome with roughly two minutes of relevant
technology news, renewed every three days. Workspace metrics are not technology news.

## Decision

Fetch only fixed HTTPS RSS endpoints from Kubernetes, GitHub's changelog and CISA.
Disallow redirects, bound decompressed bodies and reject XML entities. Retain dated
items no older than 30 days, at most two per publisher, linking only to that publisher's
HTTPS host. No private message, document or customer identifier enters an outbound
request to these feeds.

Prepare an AI summary with the confidential local alias and synthesize both languages
offline. Cache publication dates, source links, scripts and measured audio durations.
Serve that public cache without triggering generation from the unauthenticated route.
Refresh every 72 hours while the API runs; retry failed refreshes after an hour. A
stopped service catches up after restart, not via a second always-running scheduler.

Show source failures and stale state. Preserve the previous digest on incomplete
generation. Do not automatically read stale news. Welcome autoplay retains its explicit
opt-out, stop/Escape controls and browser gesture fallback. Private health briefings
still require authentication and fresh measurements.

## Alternatives rejected

An arbitrary URL fetcher would introduce SSRF. Sending workspace context to a hosted
news model would break confidentiality. Generating every visit would add latency,
cost and inconsistency. Fixed product release notes must not masquerade as live news.

## Consequences

Internet is required for feed refreshes, not for cached playback. The feed publisher
sees a standard public request and the host's network address. Summaries are AI output,
not independently verified reporting: inspect the linked announcements before acting.
Article titles retain their original language. Duration is measured rather than
guaranteed to exactly 120 seconds. Background preparation yields when an investigation
is already active but can briefly occupy the local inference engine once started.

Sources: [Kubernetes feed](https://kubernetes.io/feed.xml),
[GitHub changelog feed](https://github.blog/changelog/feed/),
[CISA advisories feed](https://www.cisa.gov/cybersecurity-advisories/all.xml).
