# ADR 0049 — Adopt the native Wolfi CA correction in LiteLLM

Date: 2026-10-22. Status: accepted.

## Context

The full rescan of the eight unchanged images, using Trivy 0.74.0 and the
22 October 07:10 UTC vulnerability database, reports one HIGH occurrence:
CVE-2026-111943 against LiteLLM's Wolfi `ca-certificates-bundle=20260611-r1`.
ADR 0044's exact G3 distrust changed effective trust but deliberately preserved
the vendor package inventory. That mitigation does not satisfy the unchanged
release gate, which refuses every CRITICAL/HIGH occurrence.

The official Wolfi package `20260909-r3` is available through the signed
repository index. Its archive SHA-256 is
`3ab79193fee767156a846f9cc91a4a0c1600741c3823fe036e007e2606c92d1f`.
The vendor's policy removes emSign G3 and C1/C3. This is broader than the earlier
local G3-only policy and must be an explicit trust decision.

## Decision

Upgrade only this native package in a new dated LiteLLM derivative. APK verifies
the official Wolfi index and package checksum; no untrusted-package option is
permitted. Pin the exact version. Check the installed package inventory and
require the native bundle SHA-256
`5961c0a3c65459931c023e0075c09733f09aea4ca439cb85bc4a08bb4f3f568b`,
its 118 effective trust anchors and G3 absence using Python's real default
OpenSSL store. Only after this succeeds may the existing distrust helper use
`--native-prepared`. No local trust-helper exception substitutes for verification.

This supersedes ADR 0044's preservation of the old native CA package and
G3-only root-set requirement **for LiteLLM alone**. The separately pinned
certifi 2026.10.19 bundle and the other seven images are unchanged. Keep both
the initial failed scan and corrected scan against the same database.

## Alternatives rejected

- Suppressing the advisory or relabeling the old package would hide evidence.
- Continuing the local G3-only policy would leave the declared gate failed.
- Rebuilding or upgrading all eight images would add unrelated changes and
  duplicate already reusable evidence.

## Consequences and evidence

The native vendor policy can reject certificate chains relying on C1/C3.
The application certifi bundle retains its own reviewed policy; neither check
certifies arbitrary custom stores, host/browser roots or all external chains.

The new local image is
`sha256:038c245f7dd8e5278e82b27686becd7add28f51a961e4382835a6d98b8d521df`.
The unchanged database now reports 0 CRITICAL/HIGH, 20 MEDIUM and 1 LOW for
LiteLLM. Real-image checks reject the former package and an altered bundle,
then accept the corrected image. The isolated gateway qualifier passes auth,
restricted aliases, migration/restart, local model transport and logical
rollback. The live stack is not changed by this qualification.

Primary references: [Wolfi package source](https://github.com/wolfi-dev/os/blob/main/ca-certificates.yaml),
[official package](https://packages.wolfi.dev/os/x86_64/ca-certificates-bundle-20260909-r3.apk),
[CVE record](https://www.cve.org/CVERecord?id=CVE-2026-111943), and
[Go advisory](https://pkg.go.dev/vuln/GO-2026-6809).
