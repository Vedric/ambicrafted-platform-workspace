# Qdrant security derivative

This small local derivative retains Qdrant 1.19.1 at its tested upstream digest
and upgrades Debian `perl-base` to exactly `5.40.1-6+deb13u1`. It closes the three
Perl critical occurrences identified in the 2026-09-26 image scan. It does not
change Qdrant's application version or claim to fix all image findings.

Build from the repository root:

```sh
docker build --pull=false \
  --tag ambicrafted/qdrant:1.19.1-security.20260926 \
  gateway/images/qdrant
```

Use this directory as the build context. Its `.dockerignore` permits only the
Dockerfile and ignore file, excluding private configuration and backup data.
APT retains its standard repository signature checks; the build fails if the
exact package version is unavailable. Do not replace that failure with an
unsigned repository or an unversioned package. A deliberate package update
requires a new dated tag and repeated validation.

The build tested on 2026-09-26 produced local image ID
`sha256:6bf8e2332c0e3a8305260a067301885ac617712e69f80458180bf9d28ea44578`.
Build timestamps and attestations can change the ID on a later rebuild; test
and scan the resulting image itself. The tag has not been published to a
registry, so another host must build and validate it or use an approved image
publication workflow with its resulting registry digest.

Validation restored a private backup with 31 vectors of 768 dimensions into a
disposable candidate, exercised readiness, querying, collection creation,
upsert, restart persistence and deletion, and then removed its storage and
network. Trivy 0.74.0 reports **0 CRITICAL / 50 HIGH**, compared with
**3 CRITICAL / 54 HIGH** in the pinned upstream image. The exact package was
verified inside the disposable candidate. The remaining highs were retained
without suppressions.

The build and tests do not themselves replace the production service.
Promotion must preserve its existing storage and use the platform's backup,
health verification and rollback procedures. See the
[release security assessment](../../../docs/SECURITY-RELEASE-2026-09-26.md)
for evidence locations, remaining findings and release limits.
