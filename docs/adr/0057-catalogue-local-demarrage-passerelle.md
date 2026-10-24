# ADR 0057 — Deterministic offline gateway startup

Date: 2026-10-24
Status: Accepted

## Context

The fresh hosted LiteLLM build failed during the real concurrent CLI consumer
test. The remote model-cost-map retry thread raced with module initialization,
raising a partially initialized `LoggerContext` import error. The earlier local
build had passed the same network-isolated test; that pass did not rule out the
race. The failure receipt is retained.

The pinned LiteLLM 1.104.4 source explicitly supports
`LITELLM_LOCAL_MODEL_COST_MAP=True` before imports. Its default fetch behavior
and pricing purpose are described in the upstream
[model cost map documentation](https://docs.litellm.ai/docs/proxy/model_cost_map).

## Decision

Set the supported environment option in the image before build checks and keep
it in the runtime. Use the catalog shipped in the immutable upstream base.
No dependency source is patched for this fix. The real four-process consumer
test additionally refuses Python socket connects and DNS lookup during imports,
while Docker also removes networking from the build step. Requalify the changed
image with the complete GPU gateway profile and a fresh advisory scan.

## Alternatives rejected

Retrying the same hosted job would hide an intermittent defect. Allowing network
in the build test would make imports depend on external availability. Setting
the option only in the test would leave the same offline startup risk in the
personal platform. Replacing upstream import code is unnecessary when its
supported configuration addresses the trigger.

## Consequences

Local startup does not need a remote pricing download. The bundled catalog
changes only with reviewed images; prices and supported model metadata may lag
a provider. Cloud spend estimates require separately verified deployment prices
or a qualified catalog/image update. Token measurements and actual provider
bills are distinct from catalog estimates. This option does not itself disable
all other gateway network activity or provider calls.
