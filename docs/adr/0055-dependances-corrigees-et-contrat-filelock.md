# ADR 0055 — Correct dependencies and qualify the local filelock contract

Date: 2026-10-24. Status: Accepted for the private Linux amd64 deployment.

## Context

The 24 October vulnerability database reports nine HIGH occurrences in the
previously qualified Grafana, LiteLLM and Qdrant images. A prior zero-HIGH report
cannot clear newly disclosed advisories. The release gate stays blocking, with
no ignore file or severity suppression.

The filelock correction is available only in the 4.x line. LiteLLM 1.104.4
declares `filelock>=3.16.1,<4.0`; the inspected 1.106.3 distribution still has
that upper bound. Installing 4.x without addressing the dependency contract
would leave an inconsistent environment. Backporting the SQLite lock fixes into
3.x would create a larger maintained fork and retain the raw HIGH finding.

## Decision

- Install signed, hash-pinned Brotli corrections: Alpine `brotli-libs=1.2.1-r0`
  in Grafana and Wolfi `libbrotlicommon1`, `libbrotlidec1`, `libbrotlienc1`
  `1.2.0-r7` in LiteLLM. Verify them with the existing base-image repository keys;
  never use unauthenticated APK installation.
- Install the official, hash-pinned pypdf 6.21.2 wheel in LiteLLM and pin the
  same version in the control API. Keep the real document-parser sandbox and
  its memory, time, filesystem and network restrictions.
- Upgrade Qdrant's UI build lock to undici 6.29.1, rebuild the complete dashboard
  and regenerate its SBOM. Preserve every unrelated lock entry, including
  optional native watcher platform selectors.
- Install the official filelock 4.2.4 wheel in LiteLLM and in the local voice
  lock. The voice consumers already permit that version. The LiteLLM derivative
  explicitly changes **one** `Requires-Dist` line to `filelock==4.2.4`, with an
  updated RECORD checksum and a persistent local-contract attestation. This is
  our qualified distribution contract, **not upstream LiteLLM support for 4.x**.

The reviewed LiteLLM consumer installs its CLI status-line script using
`FileLock(..., timeout=10, mode=0o600)`. The other installed consumer is Hugging
Face Hub, which uses `FileLock`, `SoftFileLock`, `Timeout` and `BaseFileLock`.
Neither consumer uses the `SoftReadWriteLock` on-disk protocol changed by 4.0.
All three direct-consumer source files remain byte-for-byte unchanged.

The build refuses unexpected consumer source, original METADATA or RECORD
hashes before changing installed files. The exact 4.2.4 wheel replaces the
affected implementation; no package is relabeled as fixed. Only the dependency
constraint and its RECORD entry change in LiteLLM. The attestation is
`/usr/share/ambicrafted/filelock-contract.json`. Build helpers and tests are
mounted into build stages and do not enter the runtime image.

## Alternatives rejected

- Keep the vulnerable pin because the affected SQLite lock is not currently
  called: installed vulnerable code would remain and the release gate would fail.
- Ignore the upper bound or silence dependency checks: hides a maintenance
  obligation instead of declaring and testing the actual local contract.
- Change a version string or SBOM entry without replacing/rebuilding the code:
  produces misleading security evidence.
- Move the gateway to an unrelated feature release: does not remove its filelock
  bound and introduces broader application and telemetry changes.
- Downgrade to an old 3.x release predating the vulnerable feature: discards
  intervening security and reliability corrections.

## Verification and consequences

The build tests the real LiteLLM installer with four concurrent processes and
checks serialized writes, valid output and owner-only permissions. It exercises
the real Hugging Face locks under interprocess contention, timeout, recovery,
exceptions, soft-lock fallback and shared-cache access. The installed dependency
graph must satisfy all active base requirements; `uv pip check` also passes.
Five modified-input cases demonstrate refusal before any file is written.

An isolated HTTP regression reproduces undici's excessive-content-encoding and
truncated-body failure. It fails with 6.29.0 and passes with 6.29.1, including
successful decompression of a subsequent valid response. The complete vendor UI
tests and production build run before the rebuilt artifacts enter Qdrant.

Qualify each exact image again, including real local gateway generation and
tracing, persistence, restart and rollback; run the Qdrant and Grafana browser
checks and rescan all eight images. Test the API and real offline voice after
their dependency changes. Dated qualification records the actual outcomes.

Future LiteLLM or Hugging Face upgrades must review this bounded exception
again. Remove it when upstream supports a corrected release. Preserve the
existing OTel parser backport separately: its truthful MEDIUM inventory finding
is not suppressed by this change. Zero HIGH/CRITICAL is a dated inventory gate,
not an assurance of zero vulnerabilities or autonomous model correctness.

References: [Brotli advisory](https://github.com/advisories/GHSA-9v8h-qqgm-4m35),
[pypdf 6.21.2](https://github.com/py-pdf/pypdf/releases/tag/6.21.2),
[filelock advisory](https://github.com/tox-dev/filelock/security/advisories/GHSA-v4x8-3wr5-3wq8),
[filelock changelog](https://py-filelock.readthedocs.io/en/latest/changelog.html),
[undici advisory](https://github.com/nodejs/undici/security/advisories/GHSA-xjj6-f33q-929c).
