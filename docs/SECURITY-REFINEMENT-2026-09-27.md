# Security refinement — 2026-09-27

Status: local functional qualification completed; security gate remains failed.
The rebuilt seven-image inventory contains **0 CRITICAL and 53 HIGH** findings.
Do not describe the platform as free of vulnerabilities or commercially production-ready.

## Application boundaries

The private console remains loopback-only and single-operator, with authenticated
API access, CSRF checks for session mutations, host/origin validation and bounded
requests. Saved dialogue commits complete pairs, verifies retry fingerprints and
releases the inference lease on disconnect, including a failed header send.

Document extraction runs in a bounded subprocess: size/expansion limits, hardened
XML, no macros/formula execution, metadata-stripped images, timeout and network/
child-process denial. This is not an OS sandbox. Arbitrary untrusted document
processing requires further isolation before exposing it to commercial tenants.

Graph memory uses a dedicated authenticated Neo4j database on loopback port 47474.
Its API has fixed parameterized queries and explicit scopes. NEXUS exposes two
read-only memory tools, not arbitrary Cypher. Relationships cannot cross scopes;
scopes are organizational filters, not tenant authorization boundaries.

Public technology watch accepts only fixed HTTPS publisher feeds, bounded XML and
recent dated items. Its persisted public schema is validated before exposure.
Model summaries reject invented CVE/version identifiers. These guards are not a
complete factual-verification system or a prompt-injection immunity claim.

## Container findings and promotion state

Trivy inventories dated 2026-09-27 remain in private qualification evidence under
`immersive-refinement-2026-09-27/security-*`. Counts are inventory findings, not an
exploitability assessment. No finding is hidden by deleting SBOM/package metadata.

| Component | CRITICAL | HIGH | Local state |
|---|---:|---:|---|
| LiteLLM | 0 | 0 | Pinned official image |
| PostgreSQL | 0 | 0 | Previously qualified security derivative |
| Tempo | 0 | 0 | Rebuilt, race-tested, OTLP/read/restart checks passed; installed |
| Prometheus | 0 | 0 | Pinned official image |
| Grafana | 0 | 9 | Signed plugin upgrades, datasource/dashboard checks passed; installed |
| Qdrant | 0 | 0 | Minimal runtime; persistence, snapshots, browser and migration qualified; installed |
| Neo4j | 0 | 44 | Dedicated authenticated memory; notes, links, restart and restore qualified; installed |

The [machine-readable inventory](security/image-summary-2026-09-27.json) includes
all severities. The scheduled workflow now builds and scans all seven declared
images, including the optional dedicated memory Compose file. Its HIGH/CRITICAL
threshold is unchanged and still returns failure. No suppression was added.

Grafana's remaining HIGH findings are in its main Thrift dependency and several
signed bundled plugins (gRPC and Tempo libraries). Upstream dependency fixes exist,
but patched signed plugin releases or a separately qualified build are still needed.
Editing a signed plugin binary or its SBOM would invalidate provenance, not solve
that release requirement. Neo4j findings are in retained Debian runtime packages;
the scanned distribution records no fixed version for these findings, with one
marked fix-deferred. Their exploitation is not established by this inventory.

The first source rebuild exposed that Qdrant still defaulted to its conservative
APT stage while the qualified candidate used `minimal`. The final Dockerfile now
uses the minimal final stage by default, and the complete seven-image scan was
repeated. This prevents a fresh installation from silently restoring the 43 HIGH
findings seen in that intermediate rebuild.

The Neo4j derivative removes unnecessary development headers and wget, retaining
upstream Java and package metadata. All 13 Grafana plugin signatures were valid in
the candidate test; plugin signature enforcement was not bypassed. Qdrant's minimal
runtime changes the UID and shell startup behavior, so it cannot be promoted by
blindly replacing an image tag. See the respective `gateway/images/*` recipes.

## Recovery evidence

The new graph backup is a private bounded logical export, inventoried and checksummed.
A disposable authenticated restore compared full content for two synthetic notes and
one relationship. The full platform restore also verified seven console analyses
and checkpoints, zero restored sessions/tickets, 86 PostgreSQL tables, 31 Qdrant
points and valid Grafana/agent SQLite files. Independent databases are not one
atomic snapshot; continuity backups require quiescent mutations.

## Conditions still required for a commercial production offer

Resolve or explicitly assess remaining dependency advisories, complete candidate
future patch/rollback qualification, perform an independent adversarial review and define
supported deployment configurations. A multi-customer service additionally requires
tenant isolation, RBAC, lifecycle/audit policy, secrets management and tested capacity,
SLOs and recovery objectives. The current local-private scope does not provide those
commercial service guarantees simply because its automated tests pass.


## Voice and media boundaries

The multilingual speech weights and style arrays are fixed numeric ONNX/float32
artifacts, verified before CPU inference. No pickle, remote code, user-provided IPA
commands or network inference is loaded. Text and phoneme batches have explicit
bounds; unsupported phonemes and oversized speech fail without leaving a partial
public recording. Browser music is a local original asset, never an external stream.

The production application state was backed up before image migration. Tempo also
received a private volume archive. Only this platform's `gateway_tempodata` and
`gateway_qdrantdata` ownership was migrated; other client stacks were untouched.
