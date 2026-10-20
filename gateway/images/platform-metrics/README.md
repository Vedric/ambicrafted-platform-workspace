# Platform metrics image

This derivative keeps node_exporter 1.12.1 and its qualified runtime, rebuilding
with the pinned Go compiler and module locks. The current dated image applies the
shared [exact CA distrust policy](../trust-policy/README.md) without changing the
exporter binary, metric behavior, runtime UID or package inventory.

```sh
docker buildx build --load \
  --build-context trust-policy=gateway/images/trust-policy \
  --tag ambicrafted/platform-metrics:1.12.1-security.20261021 \
  gateway/images/platform-metrics
```

Build from the repository root. The public named context is required; Compose
and the scanner supply it automatically. This local tag is not a published
registry digest. Preserve the full dated image scan, including UNKNOWN findings.
