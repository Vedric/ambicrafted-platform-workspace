# Dedicated graph-memory image

## Targeted trust correction — 2026-10-21

The current dated image additionally distrusts the exact compromised emSign ECC
G3 root in its actual operating-system trust stores. See the shared
[trust policy](../trust-policy/README.md) for the fingerprint, native Java handling,
unchanged package inventory, qualification evidence and limits. This is a local
trust-policy change, not a claim that the vendor CA package was upgraded.
The named build context below contains only public policy code and certificates;
it is required when building manually. Compose and the image scanner supply it
explicitly. Existing application binaries and features are unchanged by this step.

This profile supports the platform's **bounded JSON/Cypher note store**: authenticated
queries, scope-filtered notes, relationships, unique IDs, persisted data and logical
backup/restore. It retains the vendor's Java 21 runtime, database, authentication,
entrypoint and administrative tooling. It is not a general-purpose Neo4j bulk-import
image.

The base is the vendor-published `neo4j:5.26.32-community-ubi10`, pinned to digest
`sha256:e94e5440ea760e2f96457fa90224c26771d4d0c5cd65bf9e1da6aa812db2f776`.
The [official image manifest](https://github.com/docker-library/official-images/blob/master/library/neo4j)
lists this community/LTS variant; its source is
[pinned upstream](https://github.com/neo4j/docker-neo4j-publish/tree/3abe11cd8b22f68279adf33ba879c73e10581802/5.26.32/ubi10/community).

## Deliberate feature boundary

**Parquet bulk import is unsupported in this image.** Seven complete unused JARs
are removed: `parquet-column`, `parquet-encoding`, `parquet-jackson`, `parquet-hadoop`,
`parquet-format-structures`, `parquet-common` 1.18.1, and `parquet-floor` 1.62.
No classes are edited and no vulnerability metadata, package inventories, licenses
or scanner findings are hidden. The platform does not use these dependencies to
store notes or restore its JSON snapshots. Do not use the image for general
`neo4j-admin database import` jobs or add plugins without separately qualifying
that expanded profile.

Why this matters: the vendor image already ships top-level Jackson 2.22.3, but
`parquet-jackson-1.18.1.jar` embeds its own shaded Jackson 2.22.2. Upgrading the
ordinary Jackson JARs would not fix that copy. Maven Central had no released
Parquet 1.18.2 at qualification time. Building a private Parquet fork would add a
build toolchain and update burden for an unused feature.

The complete 2026-10-20 scan of the resulting image reported **0 CRITICAL, 0 HIGH,
1 MEDIUM and 1 LOW**. The residual findings are jline-reader 3.21.0
(`CVE-2026-77420`) and Neo4j 5.26.32 (`CVE-2026-1337`). This is a dated inventory,
not a claim of zero vulnerabilities. Release publication must rerun the complete
image audit, without ignoring unknown/unfixed findings. The Red Hat and Debian
results use their respective vendor advisories; the base switch is a supported
runtime choice, not evidence that either OS is intrinsically safe.

## Platform support

The x86_64 UBI10 runtime requires **x86-64-v3** CPU features, including their exposure
through the hypervisor. See [Red Hat's container compatibility policy](https://access.redhat.com/support/policy/rhel-container-compatibility).
The current Linux/WSL workstation is qualified. ARM64 is available upstream but has
not been qualified by these local results. Older x86 CPUs need a separately
maintained/tested runtime; do not bypass the audit to claim universal portability.

## Reproducible qualification

From the repository root, with the current control API environment synchronized:

```sh
docker build --build-context trust-policy=gateway/images/trust-policy --tag ambicrafted/neo4j:5.26.32-memory.20261021 gateway/images/neo4j
uv run --project apps/control-api --no-sync python gateway/images/neo4j/qualifier.py \
  --old-image ambicrafted/neo4j:5.26.31-security.20260927 \
  --new-image ambicrafted/neo4j:5.26.32-memory.20261021
uv run --project apps/control-api --no-sync python scripts/exercer_recuperation.py \
  --neo4j-image ambicrafted/neo4j:5.26.32-memory.20261021
```

The migration exercise creates a unique disposable named volume, starts the old
image, inserts two synthetic notes and one relationship, upgrades that same
volume, checks auth rejection and constraints, writes a change and restarts the
candidate. It separately restores the pre-upgrade logical snapshot into both the
candidate and the previous image. Its rollback means **old image plus pre-upgrade
backup**, not a promise that downgrading the upgraded physical store is safe.
Only its own generated containers/volume are removed. No production credential,
port, volume or database is read or modified.

`neo4j-admin --version` and `neo4j-admin database dump --help` are also checked
separately. The logical recovery exercise verifies actual graph content, not just
container startup. The full actual-data backup remains a separate operational
exercise; see [Recovery](../../../docs/RECOVERY.md).

Before a base/version update, reconsider whether the vendor has released a fixed
Parquet dependency. If the product later needs Parquet import, restore that
feature only with fixed upstream artifacts and its own import/compatibility tests.
The explicit JAR names fail the build if the vendor dependency set changes.
