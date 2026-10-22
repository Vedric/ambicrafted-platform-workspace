# Exact emSign ECC G3 distrust policy

This public build context removes trust in exactly one compromised CA certificate:

`86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b`

It is the SHA-256 of the DER-encoded **emSign ECC Root CA - G3**, not its subject
name. Another certificate with the same name is not removed. The certificate
fixture is public; no private key or signing credential belongs in this context.

## Reason and scope

The [certifi advisory](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2)
and [PyPA record](https://github.com/pypa/advisory-database/blob/main/vulns/certifi/PYSEC-2026-4320.yaml)
were published after the 20 October Trivy database used by the earlier candidate.
A prior zero-HIGH result therefore cannot clear this later-disclosed compromise.
The seven Python locks and the LiteLLM application use official certifi 2026.10.19.
Its unmodified bundle removes G3 while restoring the three unaffected emSign
roots removed by 2026.10.18. Actual installed bundle bytes and SSL trust anchors
are checked in the LiteLLM build, not merely the package version.

All eight earlier container OS stores still trusted G3. Python's certifi update
alone does not correct Go, native OpenSSL, Rust or Java clients. This policy
therefore changes their actual trust material while preserving package inventory
and all unaffected anchors in each pinned base. It does not change the host,
Docker daemon, browser or an operator's custom trust store.

Official package candidates were examined first. Alpine's 20261020-r0 bundle also
removed two unaffected emSign roots; Debian bookworm's 20250419~deb12u2 removed
G3 plus an unrelated AAA Certificate Services root. The UBI repository offered no
newer CA package than the pinned image. Rather than mixing unrelated root-policy
changes or replacing distro trust semantics, the derivative applies this one
reviewed, explicit distrust rule. Revisit the rule when adopting a later base.

## Implementation

Seven images execute `distrust.go` only during their final build. The helper:

- decodes each PEM certificate and compares its exact DER fingerprint;
- removes that root from effective bundles and individual certificate files,
  including aliases and hashed links resolving to the removed file;
- disables the corresponding Debian regeneration entry;
- requires a nonempty effective bundle and the expected original root;
- preserves every other certificate's encoded bytes and all package records.

It scans only the declared system certificate locations, refuses escaping fixture
links and unexpectedly large files, and records changed/deleted paths in
`/usr/share/ambicrafted/ca-distrust.json`. A changed upstream bundle requires review.
Since 22 October, LiteLLM uses `--native-prepared` only after installing the signed
Wolfi `ca-certificates-bundle=20260909-r3` package and independently verifying its
exact bundle hash, 118 effective default OpenSSL anchors and G3 absence.
That official policy also removes C1/C3; the earlier G3-only root-set assertion
below applies to the 21 October images. Other images retain the narrow helper
policy. See [ADR 0049](../../../docs/adr/0049-paquet-ca-wolfi-natif.md).
The helper and Go toolchain do not enter the final image.

Neo4j's UBI10 runtime instead uses the distribution's native
[p11-kit shared trust mechanism](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/10/html/securing_networks/using-shared-system-certificates):
the public certificate goes into `/etc/pki/ca-trust/source/blocklist`, followed by
`update-ca-trust extract`. This regenerates PEM, OpenSSL trusted bundles and Java
`cacerts` together. A blocked certificate may remain encoded in the native
OpenSSL distrust inventory; its presence there does not make it a trust anchor.
`VerifyTrust.java` exercises the JVM's **actual default trust manager** before and
after extraction. It requires the former 146 accepted issuers to become exactly
145, requires G3 verification to change from success to refusal, and leaves every
other accepted issuer unchanged. The public result is retained at
`/usr/share/ambicrafted/ca-distrust-java.json`. No JVM verification setting is relaxed.
The runtime contains no OpenSSL CLI; exported actual stores are also checked with
an external OpenSSL verifier during qualification.

Qdrant's unchanged Rust executable uses reqwest 0.13.5, rustls-platform-verifier
0.6.2 and rustls-native-certs 0.8.3. Its pinned Cargo graph has no `webpki-roots`.
Checksum-verified official crate sources show that the Linux path loads the OS
CA files/directories through native certificate discovery. This policy therefore
covers that standard path; it does not assert that arbitrary custom TLS settings
or a future crate update inherit the same behavior.

## Rebuild and checks

From the repository root, pass this exact named local context:

```sh
docker buildx build --load \
  --build-context trust-policy=gateway/images/trust-policy \
  --tag ambicrafted/tempo:3.0.3-security.20261021 gateway/images/tempo
```

Compose supplies the same `additional_contexts/trust-policy`. The image scanner
allows only this name and literal repository path; URI contexts, alternative
names, outside paths, symlinks and special files are rejected. No root checkout or
private environment directory is supplied as a Docker build context.

The build-only Go tests check exact identity, unrelated/same-name roots, trusted
PEM metadata, hashed aliases, regeneration entries and refusal of invalid/empty
stores. Runtime qualification compares old/new root sets and actual verification:
G3 succeeds before and fails after; the unaffected emSign G1 still succeeds.
The complete root sets must differ by G3 alone. Go's native system pool is tested
inside every actual old/new image. The Neo4j JVM check runs in the image build.
Server executables, Grafana signed plugin trees, Qdrant dashboard/SBOM and Neo4j
JARs are compared against the previous qualified artifacts.

Keep complete image scans and their database timestamps alongside these checks.
A package-based scanner can retain findings for the unchanged vendor CA package;
that inventory is intentional. The distrust report is additional provenance,
not a replacement version, vulnerability suppression or universal safety claim.
These local image tags are not published registry digests. Promotion still needs
the exact build identity, backup/recovery checks and a separate deployment step.
