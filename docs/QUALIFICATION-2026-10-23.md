# Personal release qualification — 23 October 2026

This report extends the [22 October qualification](QUALIFICATION-2026-10-22.md).
The product remains a private, supervised personal workspace. Public source,
repository protection, completed local tests, hosted release checks and the
running workstation are separate evidence boundaries.

The dependency corrections below are qualified within their stated scope.
**Personal promotion and release are not accepted while generation is blocked
on the reference workstation.** The [host incident](HOST-INCIDENT-2026-10-23.md)
records the separate Windows/WSL GPU-access failure and the recovery checks.

## Source publication and repository protection

The repository became public with reviewed source
`2edf79a56f4177cf67deae5a2465939b373d06be`. The final publication audit covered
the source archive, accessible Git history and pull-request heads, existing
GitHub comments/reviews, release assets and workflow logs/artifacts. Its two
remaining scanner matches were verified Go module checksums, with no unresolved
credential finding. One historical zero-job workflow attempt had an unavailable
log archive (HTTP404); that archive was not inspected. This is bounded detection
evidence, not proof that every possible secret or confidential sentence can be
recognized automatically.

Readback at 12:43 UTC confirmed 15 repository-protection checks: public source,
the intended main/tag identities, effective main and release-tag rules,
read-only default workflow tokens, required full-SHA action references,
approval before external-fork workflow execution, secret scanning and repository
push protection. No open secret alert was returned. Main requires the eight
application checks and a pull request with zero mandatory approvals, allowing
the solo maintainer to merge checked work. Release tags cannot be moved or
deleted through the ordinary workflow. The workstation is not a CI runner.

## Completed two-hour lifecycle exercise

The frozen application at
`6e216d36f68dc0136d7b96cf463463d79e534ff9` completed **7,202.118 seconds**,
**2,261 cycles** and **18,143 HTTP requests**, with 376 descendant-process
checks and three server starts. SQLite integrity passed and source hashes
remained unchanged. Peak RSS was 126,596 KiB, with nine file descriptors and
one thread. The last 10,000 analysis-read samples had p95 21.09 ms and maximum
69.38 ms; these are local reads, not voice or model-response latency.

Inference was synthetic. The exercise used real HTTP, queues, subprocesses,
restarts and persistence; it does not establish sustained GPU throughput,
physical audio behavior or uninterrupted 24-hour service. The application
API, agent and voice sources remain unchanged from that freeze. The console
logout correction below has a separate qualification; the earlier 250-case
browser result does not qualify changed browser code. The later Runbooks MCP
dependency-lock update and image changes also require their own evidence.
The two-hour exercise remains evidence for its HTTP, persistence and process
scope, not a browser soak or a later model-generation result.

## Browser logout correction

The [corrective PR's first application run](https://github.com/Vedric/ambicrafted-platform-workspace/actions/runs/39959587152)
completed seven jobs successfully but failed the console gate. Its WebKit
password/logout scenario produced an uncaught `/api/veille` access-control error
on the first attempt, then passed on retry. The configured flaky-test gate
correctly refused that result; no unchanged rerun was used to turn it green.

The retained trace places the error between the start and completion of a
document reload after a successful logout response. A public welcome query was
being mounted during document teardown. The correction keeps server-side
revocation, the session-expiration signal and cache clearing, then returns to
the welcome page through the existing SPA router with history replacement.
It removes the document teardown implicated by this trace. It does not suppress
browser errors, widen a timeout or relax `failOnFlakyTests`.

The new acceptance checks verify that the old cookie is refused, private API
requests return HTTP401, history navigation and reload remain signed out, and
a held authorized export cannot become a late download after logout. Unit tests
also hold private and authenticated-session responses until after revocation,
then verify they cannot restore the cleared state. A refused logout keeps the
workspace and reports the failure instead of claiming success.

A deterministic comparison against the old build rejects its document
replacement while the corrected build preserves the document. The rare original
WebKit exception was not reproduced locally. Back navigation and reload are
exercised; a particular native BFCache restoration is not forced or claimed.
Qualification of the complete corrected console is recorded separately from
these diagnostic and targeted checks.

A fresh, secret-free clone of signed commit
`9ca64ebcd8e68f7920134ddefd3e251016e04b4a` passes dependency installation and
audit, build, browser-test typing, formatting and **304 unit tests**. The full
configured Playwright matrix passes **254 cases** in 839.522 seconds, with zero
failed, skipped, flaky or retried cases: 33 Firefox critical paths, 38 WebKit
critical paths, five Firefox motion cases and 89 Chromium cases each on desktop
and mobile. Test discovery and execution inventories match exactly.

The source tree and built assets remain unchanged after testing. The private
receipt is bound by SHA-256
`fef7fcd3f7b9b47ce1bff12d1bf9f662304f6c8750711bc76ef623d89a80529b`,
with individual log, result and bundle manifests. Application dependencies and
assets were installed/built freshly; the pinned browser binaries and extracted
system libraries were reused. Browser inference is synthetic and physical audio
hardware is not qualified by this matrix. Final source verification requires
the complete console tree to match this measured commit; the old console result
cannot substitute for its new receipt. Hosted checks remain a separate gate.

## Refreshed image findings

The same eight local image identities were scanned with Trivy 0.74.0 and the
database updated **23 October 07:12:39 UTC**. Its SHA-256 is
`99aa7d4ff0b0ed45e7b52ee5bc87cf9181e3cb6e536fa3df6f0efe6e56e4e790`.
The totals are **0 CRITICAL, 0 HIGH, 24 MEDIUM, 9 LOW and 5 UNKNOWN**.
The increase from the previous day's 23 MEDIUM occurrences is one newly
reported OpenTelemetry API advisory in the unchanged LiteLLM image. Earlier
dated results remain accurate for their own database; they are not the current
scan result.

| Finding group | Current disposition |
| --- | --- |
| LiteLLM CVE-2026-114603, MEDIUM | Upstream parser/propagator backport and targeted gateway profile pass; raw finding retained, generation not qualified |
| Qdrant, 23 MEDIUM / 8 LOW | No fixed version listed by this database; original scope remains documented |
| Neo4j CVE-2026-1337, LOW | Vendor-documented LTS backport; raw scanner occurrence retained |
| Five Go inventory occurrences, UNKNOWN | Retained with their previous applicability limits; no blanket exemption |

[ADR 0053](adr/0053-retroportage-tracestate-litellm.md) records why the
gateway correction backports the official two-file fix without forcing an
unsupported OpenTelemetry dependency family. The package version remains
1.33.1, so the behavioral correction does not remove the raw version-based
advisory. A fresh scan of the corrected image retains one MEDIUM occurrence;
the eight-image aggregate remains 24 MEDIUM, 9 LOW and 5 UNKNOWN, with no
CRITICAL/HIGH. No scanner ignore or version relabelling was introduced.

The new local tag is `ambicrafted/litellm:1.104.4-stable-security.20261023.1`;
its exact local image ID is
`sha256:8a2f4e749f4094d00ad637d2cd7412d49a9037900c6f7eac2eb11f5c4946fcf4`.
This identifies a local artifact, not a registry digest, hosted rebuild or
already installed live revision.

## Gateway backport: observed behavior and limits

All **36 build tests** pass with networking disabled: four source/distribution
guard tests, 25 unchanged tests for the retained 1.33.1 parser/propagator,
four regressions introduced by the upstream fix, and three installed-runtime
checks. The latter include the real LiteLLM tracing callback. Modified source,
METADATA or RECORD inputs are rejected before any installed file is written.
The updated RECORD describes the two changed files honestly. The original
199 distribution versions and 19,729 other non-bytecode Python files match.

The first attempt to run the complete later 1.45.1 suite exposed an unrelated
`update()` contract difference. That failure is retained. The final suite uses
the complete installed-version contract plus every test added by the security
fix; it does not import unrelated later API behavior to satisfy that first run.

An isolated direct call to `TraceState.from_header` with a 100,000-character
whitespace run took 4.306 seconds for spaces and 7.220 seconds for tabs in the
previous image. The corrected parser completed those same two inputs in under
0.03 ms on this workstation. These are measured parser calls, not HTTP, model
or conversational latency guarantees. Separately, both single and combined
headers are accepted at length 8,192 and discarded at 8,193 while retaining
the valid traceparent.

The targeted service profile passes six recorded checks: old-key authentication,
migrated-key authentication/embeddings, real OTLP delivery with parent/state
verification, restart persistence, logical rollback and test-resource cleanup.
The gateway sends actual spans to an isolated Tempo instance. Alias restriction
checks also execute within the authentication/embedding path.

The full exercise timed out during generation. A narrower diagnostic explicitly
records `generation_requested=false`, `profile_passed=true` and `passed=false`.
It therefore cannot satisfy the full gateway or personal-release gate. Direct
Ollama generation also timed out while embedding remained responsive; the host
incident is investigated separately. No live database or service was changed by
the image qualification.

Five separate qualifier-verdict tests check that the limited profile cannot
satisfy full acceptance and that missing, substituted or failed required checks
are rejected. The candidate image manifest intentionally sets its complete
qualification flag to false; the release assembler refuses it. This is a
verified release guard, not a suppressed failure.

## Runbooks dependency correction

The hosted application run on the first public commit detected the same
advisory in the Runbooks MCP lock, where API 1.44.0 was still selected. The audit
correctly failed. This project does not install the OpenTelemetry SDK that
constrains LiteLLM, so it can update the API alone to the official 1.45.1 release.
The correction is restricted to that package's lock entry; the other 57
resolved packages remain unchanged. The pinned uv 0.13.4 tool also normalizes
the lock format revision from 3 to 5, without changing other metadata.

A fresh clone of signed commit
`ab85c0e2d44d572e3f8528d577b9c4cf7607131c` passes locked installation,
48 tests with 74% coverage, lint and the dependency audit. A subsequent offline
locked sync also passes. A real stdio MCP handshake lists four tools and
exercises synthetic listing, source read and search, with path-escape refusal
and a failed outbound-network control (errno 101). It uses no live service.
The qualified lock SHA-256 is
`65be0358d40b502fa5cb091b8d26ed1889abb650d51dac90fd1d3d2740800fdf`.

This proof replaces the earlier local Runbooks dependency result. The release
assembler verifies the exact lock change, the fresh receipt and actual log
hashes, then requires an unchanged MCP tree between the measured commit and the
final source. It rejects an unrelated dependency/source change or missing new
evidence. An otherwise unchanged baseline is not used to waive this correction.

## Release and operating boundary

The [release attempt for `v0.5.0-rc.2`](https://github.com/Vedric/ambicrafted-platform-workspace/actions/runs/39955362564)
was cancelled after the fresh finding was identified. Its tag remains immutable;
it is not relabelled as a successful release. In the separate main CI run, the
[Runbooks dependency-audit job failed](https://github.com/Vedric/ambicrafted-platform-workspace/actions/runs/39955363091/job/120419757779);
that failure is retained. The main application run completed with seven successful
jobs and this one failed audit. Source publication does not depend on representing
either attempt as successful. A corrective source PR can be reviewed and merged
after its required checks pass. A new personal prerelease additionally needs
every hosted application and image gate, restored generation, the complete
gateway exercise, a final public-surface audit and preserved-data local promotion.
An unpublished draft, if created by hosted CI, does not waive those conditions.

The remaining operator tasks and model limitations in the previous qualification
still apply: physical microphone/speaker acceptance, representative task review,
an independently protected off-host recovery copy and keys, an actual external
alert recipient where needed, and host reboot/second-machine checks. The four
new model scenarios yielded only one engineering-acceptable answer under AI
review. No autonomous expert, commercial-service or zero-vulnerability label
is justified by the completed infrastructure tests.
