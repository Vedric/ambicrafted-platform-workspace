# ADR 0053 — Correct OpenTelemetry within each supported dependency graph

Date: 2026-10-23

Status: Source correction, Runbooks lock and targeted gateway checks qualified
locally. Full generation and personal deployment acceptance remain blocked by
the reference host's GPU-access incident.

## Context

A fresh scan of the unchanged, previously qualified eight-image set adds one
MEDIUM occurrence: CVE-2026-114603 / GHSA-xcq7-p3pf-p88h in LiteLLM's
`opentelemetry-api==1.33.1`. The published correction is in 1.45.1. Malformed
`tracestate` headers can make the earlier regular-expression split consume
quadratic CPU time before the parser reaches its member-count check.

LiteLLM's installed SDK and semantic-conventions packages require API 1.33.1.
Its proxy-runtime extra also pins SDK/exporters 1.33.1 and instrumentation
0.54b1. The reviewed official LiteLLM tags 1.104.5 and 1.106.2 retain those
requirements. Replacing the API alone would break this declared dependency
graph; forcing the entire OpenTelemetry family would also contradict the
application's supported pins. A newer LiteLLM label is therefore not evidence
that this particular defect is fixed.

The actual LiteLLM OpenTelemetry callback forwards incoming trace context to
the affected extraction path when configured. A loopback gateway and a private
operator reduce exposure but do not repair the library. The separate control
API already resolves OpenTelemetry 1.45.1 and does not forward incoming
`tracestate`; these facts do not remove the gateway's affected package.

The fresh hosted Runbooks MCP dependency audit separately reports the same
advisory in its locked API 1.44.0. This project has no installed OpenTelemetry
SDK with an exact API pin. A direct locked update to the official API 1.45.1
therefore has a different compatibility boundary from LiteLLM.

## Decision

Update the Runbooks MCP lock to official `opentelemetry-api==1.45.1`, retaining
the other 57 resolved packages. The pinned CI tool, uv 0.13.4, also normalizes
the lock format revision from 3 to 5; other top-level metadata is unchanged.
Validate that structural lock difference,
install the resulting commit in a fresh environment, rerun its tests/lint,
dependency audit and a real MCP handshake. Reuse prior evidence only for
unchanged projects; the changed MCP dependency needs its own recorded proof.

Backport the two production-file changes from upstream commit
`d5224bf4ffdf2aee1b592ad238dcc32ca957f26b` into the pinned LiteLLM derivative.
The affected paths are `opentelemetry/trace/span.py` and
`opentelemetry/trace/propagation/tracecontext.py`. The former replaces the
backtracking delimiter split with a direct comma split and optional-whitespace
handling; the latter rejects a combined tracestate length above 8,192 characters
before invoking that parser. This is the upstream character-count behavior,
not a newly claimed byte limit or a general HTTP-request size policy.

Bind the backport to the exact installed package and expected source bytes.
Unexpected upstream drift must fail the build rather than applying a heuristic
replacement. Retain the upstream copyright and Apache-2.0 notices, record the
origin and identify the derivative's modifications. Keep the published package
version and inventory truthful. The installed API remains version 1.33.1 with
a documented source backport; it must not impersonate the 1.45.1 distribution.
Refresh the two changed files' hashes and sizes in the distribution's RECORD;
retain its METADATA bytes and the rest of the declared dependency family.

The actual image passes four source/distribution guard tests, 29 upstream tests
(the complete 25-test retained 1.33.1 parser/propagator contract plus four tests
introduced by the security fix), and three runtime/cohort/callback tests. These
36 tests run without network access in the image build. A separate old/new
adverse-input comparison reproduces the earlier slow parser and verifies the
corrected parser and combined-header boundaries.

The isolated gateway profile passes authentication, alias restrictions,
embeddings, key migration/restart, logical rollback and real OTLP delivery to
Tempo. Its caller-parent and tracestate checks preserve a valid context and
discard the oversized state. That diagnostic explicitly omits generation:
`profile_passed=true` and `passed=false` remain separate fields. The attempted
full gateway exercise timed out; direct generation below the gateway was also
unavailable during a Windows/WSL GPU-access incident. Do not reuse an older
generation success or reinterpret the limited profile as a full pass. The exact
image, counterexample and scope appear in the
[23 October qualification](../QUALIFICATION-2026-10-23.md).

The raw Trivy advisory remains visible because version-based detection cannot
infer this backport. Do not add a CVE ignore, relabel the package, rewrite an
inventory to hide the occurrence or relax the release severity gate. Separate
the observed source-level correction from the retained package-version finding.

## Alternatives rejected

- Upgrading only `opentelemetry-api` to 1.45.1 despite the installed SDK and
  semantic-conventions exact requirements.
- Forcing a complete telemetry-family upgrade outside LiteLLM's declared
  proxy-runtime graph, or upgrading LiteLLM to a reviewed tag that retains the
  affected pins.
- Treating loopback binding or a MEDIUM classification as remediation.
- Suppressing the advisory so the old zero-finding image summary still appears
  current.

## Consequences

This narrow backport creates an explicit derivative-maintenance obligation.
Recheck the patch and its source guards whenever the base image changes. Prefer
a supported vendor dependency graph containing the fix once available; retire
the backport only after equivalent behavioral and gateway checks pass. Do not
quietly retain the patch across unrelated source changes.

The 23 October unmodified-image scan reports 0 CRITICAL, 0 HIGH, 24 MEDIUM,
9 LOW and 5 UNKNOWN occurrences. A backport does not retroactively change that
scan, remove its raw advisory or establish the absence of other vulnerabilities.
Re-scanning the corrected image against that same database retains its one
MEDIUM record, leaving the aggregate unchanged. Its 199 installed distribution
versions remain identical; only the two production Python files and their
RECORD entries differ among 19,732 non-bytecode package files.
The previous release attempt and immutable tag remain historical. A corrected
candidate requires its own hosted qualification. Publishing the reviewed source
correction does not require calling the unavailable host healthy; personal
promotion/release still requires recovered generation and preserved-data checks.

References: [upstream advisory](https://github.com/advisories/GHSA-xcq7-p3pf-p88h),
[official corrective commit](https://github.com/open-telemetry/opentelemetry-python/commit/d5224bf4ffdf2aee1b592ad238dcc32ca957f26b),
[LiteLLM 1.104.5 requirements](https://github.com/BerriAI/litellm/blob/v1.104.5/pyproject.toml),
[LiteLLM 1.106.2 requirements](https://github.com/BerriAI/litellm/blob/v1.106.2/pyproject.toml).
