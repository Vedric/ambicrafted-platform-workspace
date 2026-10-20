# ADR 0044 — Exact emSign ECC G3 distrust across runtime trust stores

- Date: 2026-10-21
- Status: Accepted for the candidate; deployment is separate

## Context

A newly published CA-compromise advisory invalidated the earlier candidate's
security conclusion after its vulnerability database had been generated.
Updating certifi alone left the affected root trusted in all eight OS image
stores and Neo4j's default JVM store. Qdrant's Linux Rust client uses native roots,
not an embedded webpki root set. The host trust store is independently managed.

## Decision

Use the official certifi 2026.10.19 wheel and seven regenerated locks. Verify its
actual installed PEM hash and effective anchors. Update Pillow to official 13.0.0
for the newly disclosed decoder flaws, after migration review and real sandbox
image tests; retain supported PNG/JPEG/WebP behavior and format/size restrictions.

Apply a shared build-only policy matching only DER SHA-256
`86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b`.
Seven images remove it from real native CA bundles, source files and hashed
aliases. Neo4j uses UBI's native blocklist plus `update-ca-trust extract`, preserving
p11-kit/OpenSSL/JVM semantics. Default Java trust verification and issuer-set
equality are mandatory build checks. Runtime application binaries, package
inventories and all unrelated trust anchors remain unchanged by this OS step.

One exact local named Docker build context holds the public policy. Compose and
the scanner both supply it, with strict local-path/name/symlink checks in the
scanner. Pinned build tools are not copied into runtime images. See the complete
[implementation and evidence contract](../../gateway/images/trust-policy/README.md)
for sources, limitations, actual-store verification and rebuild instructions.

## Alternatives rejected

- Certifi-only upgrade: leaves native/Java clients trusting the compromised root.
- Disable TLS verification or suppress the advisory: breaks the trust boundary.
- Delete CA package metadata or relabel its version: misrepresents the artifact.
- Copy one generic bundle into every image: breaks native Java/p11-kit policy and
  changes unrelated roots.
- Upgrade the first available vendor CA package: inspected Alpine/Debian packages
  also removed unrelated roots; UBI had no corrected package. The chosen policy
  deliberately keeps this incident response narrower than a distro root refresh.
- Rebuild Qdrant's Rust server merely to change CA handling: its verified native
  loader already uses the corrected OS stores; a server fork adds no needed fix.
- Eight copies of the correction code: unnecessary divergence and maintenance.

## Consequences

The artifact carries truthful local policy provenance while the original CA
package versions remain visible. Real verification refusal and preservation of
unaffected roots matter independently of a scanner's package-level conclusion.
Future base/CA updates must reconsider this patch; an unexpected missing root
fails the generic build instead of silently changing its contract.

The host, Docker daemon, browser and operator-added roots are not changed by
container builds. Their correction is an explicit administrative task documented
separately. Fresh-clone qualification, remaining MEDIUM/LOW/UNKNOWN findings and
actual deployment state must be reported without reusing pre-advisory scans as
current clearance. No source or runtime change is a promise of zero future CVEs.
