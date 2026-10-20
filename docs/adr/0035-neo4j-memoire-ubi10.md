# 0035 — Vendor UBI10 runtime for the dedicated Neo4j memory profile

Date: 2026-10-20. Status: implementation under release qualification.

## Context and evidence

The Neo4j 5.26.32 community Debian/trixie image audit contains 114 HIGH OS
occurrences and four HIGH Java occurrences. Replacing it with a home-built
Java/distroless bootstrap would transfer responsibility for authentication,
configuration, permissions, JVM options and lifecycle behavior to this project.

The vendor also publishes a 5.26.32 community UBI10 image. Its complete audit
contains no reported OS vulnerabilities and the same four HIGH Java occurrences.
Those four occurrences are inside the shaded `parquet-jackson-1.18.1.jar`, not the
top-level Jackson 2.22.3 JARs. Maven Central still lists Parquet 1.18.1 as the newest
release; upstream has a Jackson update on its development branch.

## Decision

Use the vendor-maintained UBI10 image pinned by digest, preserving Neo4j 5.26 LTS,
Java 21, bootstrap, auth and administrative lifecycle. Remove the seven actual
Parquet dependency JARs as a complete unused bulk-import feature. Keep all package
metadata and licenses; do not suppress findings or edit shaded classes.

This is explicitly a graph-memory profile. The platform's bounded Cypher/JSON
notes and logical snapshots do not use Parquet. General Parquet/bulk-import jobs
are not supported by this derivative and require a separately qualified image.

The image must pass real auth, notes/relationships, constraint, persisted restart,
old-to-new upgrade and pre-upgrade-backup rollback tests, plus the complete image
audit. Container startup alone is insufficient. Runtime configuration and Compose
ports/resources stay governed by the existing private-memory contract.

## Alternatives and tradeoffs

- Keep trixie and remove essential OS libraries: rejected because deleting runtime
  dependencies or falsifying their inventory would reduce reliability/security.
- Build custom distroless startup: rejected while an upstream-maintained runtime
  exists; the maintenance burden is disproportionate to a two-note/relationship
  storage API.
- Rebuild Parquet from a patched source commit: feasible but adds a Maven build
  and private artifact maintenance for functionality the product does not use.
- Replace only unshaded Jackson: insufficient, since the affected classes are
  separately shaded into Parquet's artifact.

UBI10's x86_64 minimum is x86-64-v3. Record this in the supported-machine matrix;
this change is not a claim that all x86 machines are supported. ARM64 needs its own
qualification. Different distro advisory feeds do not prove relative exploitability.
The resulting scan still reports one MEDIUM and one LOW; keep them visible and
reassess at every release. The policy's HIGH/CRITICAL gate remains unchanged.

References: [vendor image source](https://github.com/neo4j/docker-neo4j-publish/tree/3abe11cd8b22f68279adf33ba879c73e10581802/5.26.32/ubi10/community),
[Neo4j runtime requirements](https://neo4j.com/docs/operations-manual/current/installation/requirements/),
[Parquet Maven release inventory](https://repo.maven.apache.org/maven2/org/apache/parquet/parquet-jackson/maven-metadata.xml),
[Red Hat container compatibility](https://access.redhat.com/support/policy/rhel-container-compatibility).
See the [image profile and qualification commands](../../gateway/images/neo4j/README.md).
