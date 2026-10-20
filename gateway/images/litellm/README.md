# Qualified LiteLLM derivative

The Dockerfile uses the immutable official `main-v1.104.4-stable` image and
replaces only `aiohttp` 3.14.3 → 3.14.4 and its required `yarl` 1.25.1 dependency.
The old yarl 1.23.0 does not meet the corrected aiohttp requirement. Both wheels
are official PyPI CPython 3.13 Linux x86-64 artifacts, pinned by URL and SHA-256.
Installation uses verified uv 0.12.5, offline, with no dependency re-resolution.
No build tools or wheels are copied into the final runtime.

This deliberately follows a stable upstream line. It does not adopt an unrelated
feature release merely because its version number is higher. Upstream application
code, database migration machinery and package metadata remain intact.

```sh
docker buildx build --load -t ambicrafted/litellm:1.104.4-stable-security.20261020 gateway/images/litellm
uv run --locked --project apps/control-api python gateway/images/litellm/qualifier.py \
  --old-image 'ghcr.io/berriai/litellm:v1.102.1@sha256:87f34979b9f8cb274fac90ca8a4fdda07d8480de22755562a26adeb95ce20d02' \
  --new-image ambicrafted/litellm:1.104.4-stable-security.20261020 \
  --postgres-image ambicrafted/postgres:16.15-alpine-security.20261020 \
  --output /absolute/private/new-gateway-qualification.json
```

The qualifier creates its own network, databases and credentials. It tests
anonymous/wrong-key rejection, the confidential alias allowlist, preservation of
a real virtual key through migration and restart, real local streaming/embeddings,
and restoration of a pre-upgrade dump into a separate old-version database.
Only synthetic prompts reach the configured local model. It never restores or
modifies the workstation database. It needs Docker, the reviewed gateway config
and local model availability; it does not prove every LiteLLM provider works.

The 20 October scan found 0 CRITICAL / 0 HIGH and 16 MEDIUM occurrences.
Keep the full scan and migration evidence for the exact built image. A future
upstream update must rerun both; upgrading a tag alone is not qualification.
