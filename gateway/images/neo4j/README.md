# Dedicated Neo4j memory runtime

This local derivative retains the pinned upstream Neo4j 5.26.31 Community runtime
and removes unused development headers and wget. It does not remove vulnerability
metadata or alter Java libraries. No runtime APOC/plugin downloads are supported.

Build using only this directory as context:

```sh
docker build -t ambicrafted/neo4j:5.26.31-security.20260927 gateway/images/neo4j
./plateforme memoire installer
```

The dated tag is a local build output, not a registry publication. The upstream
image is digest-pinned. Qualification on 2026-09-27 tested anonymous denial,
authenticated notes/relationships, restart persistence and cleanup in a disposable
database. Its scan still reports **44 HIGH**, **0 CRITICAL** advisories, down from
135 HIGH and 1 CRITICAL in the upstream image. This is not a zero-vulnerability
or production certification; consult the security refinement report.

The main platform uses only the dedicated loopback port 47474. Client Neo4j
databases, credentials and volumes must never be selected as substitutes.
