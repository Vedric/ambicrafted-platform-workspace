# Qualified LiteLLM derivative

## Targeted trust correction — 2026-10-21

The current dated image additionally distrusts the exact compromised emSign ECC
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
docker buildx build --load --build-context trust-policy=gateway/images/trust-policy -t ambicrafted/litellm:1.104.4-stable-security.20261021-r2 gateway/images/litellm
uv run --locked --project apps/control-api python gateway/images/litellm/qualifier.py \
  --old-image 'ghcr.io/berriai/litellm:v1.102.1@sha256:87f34979b9f8cb274fac90ca8a4fdda07d8480de22755562a26adeb95ce20d02' \
  --new-image ambicrafted/litellm:1.104.4-stable-security.20261021-r2 \
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
