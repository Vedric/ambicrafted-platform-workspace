# Qualified LiteLLM derivative

## PDF dependency correction — 2026-10-22

The current `1.104.4-stable-security.20261022.1` build also upgrades
`pypdf` **6.19.0 → 6.21.1**. The same version is pinned in the control API.
The official advisories cover excessive stream-filter memory consumption,
truncated-xref and cyclic-tree loops, and selection of an unintended Pillow
image parser. The common minimum fixed version is 6.21.1:
[stream filters](https://github.com/py-pdf/pypdf/security/advisories/GHSA-7mh2-4gg2-979f),
[xref](https://github.com/py-pdf/pypdf/security/advisories/GHSA-39mj-jf6j-2qj3),
[outline lookup](https://github.com/py-pdf/pypdf/security/advisories/GHSA-qfv9-64jg-mh7p),
[tree removal](https://github.com/py-pdf/pypdf/security/advisories/GHSA-9mx8-4j7g-633p),
[JPEG parser selection](https://github.com/py-pdf/pypdf/security/advisories/GHSA-5hx5-vpf9-5wcv).

The earlier Trivy report already contained these five findings as four MEDIUM
and one LOW occurrence. They passed the image CRITICAL/HIGH threshold; the
control API's stricter Python dependency audit then blocked qualification.
Passing that image threshold was not evidence of absence of these advisories.

The official universal wheel is pinned by URL and SHA-256 and installed with
the existing offline, hashed uv procedure. A real-image check verifies both
the imported and metadata versions and compares 63 installed files against
the official wheel, excluding installer-managed RECORD. No additional runtime
dependency or sandbox mount/syscall permission is introduced. The new Brotli
extra remains optional and is not installed by this change. Pillow is present
in the API but absent from the LiteLLM Python distribution inventory; the
remaining advisories still justify updating both consumers.

Local qualified image ID:
`sha256:6f6acda142dbfa686630b69046b88c9a056ceaae0b6aae05832f2582d5830a73`.
The same 22 October Trivy database reports 0 CRITICAL, 0 HIGH, 16 MEDIUM,
0 LOW and 0 UNKNOWN occurrences. A separate pip-audit 2.10.1 pass reports
zero known vulnerabilities across all 199 installed Python distributions,
with none skipped. The real native trust-store check and the isolated gateway
migration, stream, embedding, schema, restart and logical rollback qualifier
pass again for this exact image. The API passes 95 targeted parser, sandbox,
prerequisite and conversation tests; its 74 production dependencies pass the
same Python audit. These results do not replace the final hosted release gates.

## Native CA package correction — 2026-10-22

The first `1.104.4-stable-security.20261022` build additionally upgrades
Wolfi `ca-certificates-bundle` from `20260611-r1` to **`20260909-r3`**. The
22 October vulnerability database reports the older package as HIGH under
[CVE-2026-111943](https://www.cve.org/CVERecord?id=CVE-2026-111943), even though
the earlier local policy had removed G3. The release gate still rejects that
finding; no suppression or package-version relabeling is used.

APK authenticates the official Wolfi repository index and package checksum.
`verify_system_trust.py` then requires the exact native package version,
the complete installed bundle SHA-256, all 118 expected effective OpenSSL
anchors, and absence of G3. The shared helper runs with `--native-prepared`
only after this independent native check succeeds. Unlike the earlier narrow
policy, the official package also removes emSign C1 and C3; this follows
the reviewed vendor policy and may reject chains relying on those roots.
The separately verified certifi 2026.10.19 bundle remains unchanged.
See [ADR 0049](../../../docs/adr/0049-paquet-ca-wolfi-natif.md).

The exact local image ID is
`sha256:038c245f7dd8e5278e82b27686becd7add28f51a961e4382835a6d98b8d521df`.
Trivy 0.74.0 with the database updated on 22 October at 07:10 UTC reports
0 CRITICAL, 0 HIGH, 20 MEDIUM, 1 LOW and 0 UNKNOWN occurrences. The real-image
checks accept this bundle and reject both the older package and a modified
bundle. The isolated qualifier passes authentication, alias restrictions,
migration/restart, local streaming/embeddings, structured response, logical
rollback and resource cleanup. These are local proofs; they do not assert
hosted release acceptance or deployment to the live stack.

## Targeted trust correction — 2026-10-21

The 21 October image additionally distrusts the exact compromised emSign ECC
G3 root in its actual operating-system trust stores. See the shared
[trust policy](../trust-policy/README.md) for the fingerprint, native Java handling,
unchanged package inventory, qualification evidence and limits. This is a local
trust-policy change, not a claim that the vendor CA package was upgraded.
The named build context below contains only public policy code and certificates;
it is required when building manually. Compose and the image scanner supply it
explicitly. Existing application binaries and features are unchanged by this step.

The Dockerfile uses the immutable official `main-v1.104.4-stable` image and
replaces only `aiohttp` 3.14.3 → 3.14.4, its required `yarl` 1.25.1 dependency,
and `certifi` 2026.4.22 → 2026.10.19.
The old yarl 1.23.0 does not meet the corrected aiohttp requirement. The aiohttp/yarl wheels
are official PyPI CPython 3.13 Linux x86-64 artifacts; certifi uses the universal
Python wheel. All three artifacts are pinned by URL and SHA-256.
Installation uses verified uv 0.13.4, offline, with no dependency re-resolution.
No build tools or wheels are copied into the final runtime.

This deliberately follows a stable upstream line. It does not adopt an unrelated
feature release merely because its version number is higher. Upstream application
code, database migration machinery and package metadata remain intact.

```sh
docker buildx build --load --build-context trust-policy=gateway/images/trust-policy -t ambicrafted/litellm:1.104.4-stable-security.20261022.1 gateway/images/litellm
uv run --locked --project apps/control-api python gateway/images/litellm/qualifier.py \
  --old-image 'ghcr.io/berriai/litellm:v1.102.1@sha256:87f34979b9f8cb274fac90ca8a4fdda07d8480de22755562a26adeb95ce20d02' \
  --new-image ambicrafted/litellm:1.104.4-stable-security.20261022.1 \
  --postgres-image ambicrafted/postgres:16.15-alpine-security.20261021 \
  --output /absolute/private/new-gateway-qualification.json
```

The qualifier creates its own network, databases and credentials. It tests
anonymous/wrong-key rejection, the confidential alias allowlist, preservation of
a real virtual key through migration and restart, real local streaming/embeddings,
a JSON-schema-constrained response, and restoration of a pre-upgrade dump into a
separate old-version database. The structured-response check validates transport
compatibility and the returned shape, not factual correctness.
Only synthetic prompts reach the configured local model. It never restores or
modifies the workstation database. It needs Docker, the reviewed gateway config
and local model availability; it does not prove every LiteLLM provider works.

The earlier 20 October scan found 0 CRITICAL / 0 HIGH and 16 MEDIUM occurrences.
That database predates the newly published
[certifi CA compromise advisory](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2),
so that result does not clear the old image of the later-disclosed issue.
The [PyPA record](https://github.com/pypa/advisory-database/blob/main/vulns/certifi/PYSEC-2026-4320.yaml)
recommends 2026.10.19, which removes the affected emSign ECC G3 trust anchor
while restoring the three unaffected emSign roots removed by 2026.10.18.

The 21 October build installs the actual official wheel offline and verifies
the complete installed PEM SHA-256 and the effective OpenSSL trust anchors.
The affected root must be absent and the three unaffected roots must remain.
`verify_certifi.py` fails closed on a different version or bundle. The certifi bundle is never edited locally, and no scanner inventory is suppressed.
The separate OS trust correction is described above.
This checks the application's certifi bundle; it does not replace unrelated
host/browser trust stores or prove every external certificate chain works.

Keep the full scan and migration evidence for the exact built image. A future
upstream update must rerun both; upgrading a tag alone is not qualification.
