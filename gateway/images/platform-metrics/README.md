# Platform metrics image

## Additional native trust correction — 22 October 2026

The current dated image also removes the exact Comodo AAA root required by
[DSA-6572-1](https://www.debian.org/security/2026/dsa-6572), after the earlier G3
correction. All other anchors and application executable bytes are unchanged.
The effective bundle now contains 148 roots; native Go verification accepts AAA
in the previous image and refuses it in the corrected image, while the unrelated
control remains accepted. See the [shared policy](../trust-policy/README.md) for
both fingerprints, provenance and the distinction from a native package update.
No finding or package inventory is suppressed.

This derivative keeps node_exporter 1.12.1 and its qualified runtime, rebuilding
with the pinned Go compiler and module locks. The current dated image applies the
shared [exact CA distrust policy](../trust-policy/README.md) without changing the
exporter binary, metric behavior, runtime UID or package inventory.

```sh
docker buildx build --load \
  --build-context trust-policy=gateway/images/trust-policy \
  --tag ambicrafted/platform-metrics:1.12.1-security.20261022 \
  gateway/images/platform-metrics
```

Build from the repository root. The public named context is required; Compose
and the scanner supply it automatically. This local tag is not a published
registry digest. Preserve the full dated image scan, including UNKNOWN findings.
