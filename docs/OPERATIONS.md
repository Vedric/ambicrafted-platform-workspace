# Operations

Run commands from the checkout root unless another directory is shown. Never
print `.env`, resolved Compose configuration, response bodies containing keys,
or container environments. Scripts below keep credential values out of output.

## Daily checks

```sh
uv run --locked scripts/plateforme.py verifier
cd gateway && docker compose ps
```

The checker reports service health, restricted aliases, refusal of an external
alias, model digests, index presence and free disk space. It uses synthetic
content for the routing refusal probe. It does not measure model correctness.
Tempo readiness and exporter errors are also visible through local Prometheus
metrics and the provisioned Grafana dashboard `plateforme-sre`.

The dashboard and rules are versioned under `gateway/observability`. Rules
create local alerts; no Slack, email or other notification destination is
configured. Configure a destination only after deciding what metadata may leave.

The provisioned data sources use `Plateforme Tempo` and `Plateforme Prometheus`
with stable UIDs. Older sources named `Tempo` and `Prometheus` remain available
so their generated UIDs and existing dashboards are preserved during upgrades.

## Backups and restore drills

```sh
uv run --locked scripts/sauvegarder.py
uv run --locked scripts/tester_restauration.py /path/printed/by/the/backup
```

Backups live under `~/.local/state/platform-backups/<UTC timestamp>`, directory
0700 and files private. They include root/gateway secrets, a PostgreSQL custom
archive, coherent SQLite backups of Grafana and the graph, and a snapshot of
the active runbook index. They are confidential local data, not Git artifacts.
A `manifest.json` must say `complet=true` before a backup is used.

The restore drill creates uniquely named temporary PostgreSQL and Qdrant
containers, restores actual backup data, checks the restored schema/points,
checks SQLite integrity, and removes only those containers. PostgreSQL runs
with no network; Qdrant is published on a temporary loopback port with
telemetry disabled. The drill never replaces running services.

PostgreSQL archives are restored with `--no-owner --no-privileges` in the
drill. Production recovery additionally requires verifying roles and grants.
Grafana is integrity-checked as SQLite; the drill does not prove every plugin
or dashboard migration. Tempo/Prometheus history is not included in this
backup set. Preserve their volumes when updating services.

Checkpoints created before the delivery-contract version was introduced cannot
be resumed for approval. Re-enter the incident under a new thread so provenance
and confidentiality guards run again. Old checkpoint files and backups can
still contain raw alerts from the previous implementation; apply their retention
policy or explicitly purge reviewed obsolete threads. Upgrading code does not
rewrite every historical SQLite page or backup.

For a production recovery, stop affected writers, keep a copy of the current
volumes, restore PostgreSQL into a fresh database/volume using the archived
credentials, restore the SQLite files with their original ownership, restore
Qdrant snapshots into fresh physical collections, then re-create the alias
mapping recorded in the manifest. Start the pinned service versions and rerun
the health/routing/index checks before redirecting use. Do not restore over a
live database or assume an image downgrade reverses a schema migration.

## Console recovery

The local service is installed with `./plateforme installer-service --demarrer`.
Use `systemctl --user status ambicrafted-console.service` and
`journalctl --user -u ambicrafted-console.service` for lifecycle diagnostics;
HTTP access logging is disabled. The API binds only to `127.0.0.1:8787`.
See [CONSOLE.md](CONSOLE.md) for the operator commands and private login flow.

On restart, queued, executing and decision-in-progress jobs become interrupted;
the server never silently replays an alert. Pending human approvals remain
available. Cancel or explicitly resubmit interrupted work after verifying what
happened. Only one control process can own a state directory.

Backups include a sanitized console SQLite snapshot and individual graph
checkpoints. Sessions and login tickets are removed in memory before writing the
snapshot. Each database snapshot is coherent, including committed WAL data, but
the collection is **not atomic across databases**. Inspect interrupted and pending
jobs after a disaster recovery. Restoring the console while writers are running
is not supported. Stop the service, keep a private copy of the current state,
restore into a new private state directory, then restart and inspect it. Never
reuse the previous `-wal`, `-shm` or journal files beside a restored database.
Reconfigure the state path or replace the stopped directory as a whole, keeping
the old private directory for rollback. Authenticate again after recovery.
The restoration test checks copies only; it does not activate restored data.

## Scheduling and retention

```sh
uv run --locked scripts/plateforme.py installer-retention
systemctl --user list-timers platform-backup.timer sre-agent-retention.timer
systemctl --user status platform-backup.service sre-agent-retention.service
```

The installer writes user units using the current checkout and executable paths.
It does not print or embed secret values in unit files. Daily backup runs near
02:45 and retention near 03:15, in the user's systemd timezone, with jitter.
The user manager must remain available. `Persistent=true` catches missed events
when it next runs; this is not host high availability.

Retention removes graph threads inactive for more than 14 days and backups
created more than 14 days ago. Scheduling adds up to a day, or host downtime.
Only backup directories with the generated naming convention and manifest are
removed. SQLite purge vacuums pages and truncates WAL. External filesystem
snapshots and manually copied files require separate retention.

```sh
uv run --locked --directory agents/sre-agent --extra graphe sre-agent-graph --purger --simulation
```

The timer suppresses normal output so thread identifiers are not copied into
long-lived journal messages. Check unit exit status for failures. Removing the
checkout or its virtual environment breaks the scheduled commands; rerun the
installer after moving the checkout.

## Runbooks and index versions

1. Review runbook content, preconditions, verification and rollback with the
   service owner. Keep each actionable paragraph self-contained.
2. Run the indexer with `--dry-run`, then without it.
3. Check representative known and unknown questions. Semantic scores are not
   a correctness certificate.
4. Inspect the current alias before deleting any old collection.

`runbooks-current` points to a versioned physical collection. A failed write
leaves the previous alias untouched. An ambiguous network error during the
alias update requires checking which version is active. The old collection
is retained either way. Keep a known-good rollback version; remove unused
versions explicitly after confirming no alias references them.

The index detects a corpus fingerprint mismatch and refuses stale semantic
results. Literal search remains available. On an installation with the old
physical `runbooks` collection, index to `runbooks-current`, then update the
root `QDRANT_COLLECTION`; the historical collection is not deleted automatically.

## Updates and rollback

Review [dependency findings](DEPENDENCIES.md), select exact versions, pull them,
and record immutable digests after starting those images in an isolated stack.
Before applying to the working stack, create a backup and run the restore drill.
Test gateway schema migrations against a restored copy in an internal Docker
network. Preserve the previous Compose/config files alongside the backup.

```sh
cd gateway
docker compose config --quiet
docker compose up -d --build --wait --wait-timeout 180
```

Then check model routing, embedding dimensions, MCP reads/search, an incident
analysis, graph approval/refusal, metrics targets and the dashboard. A failed
upgrade requires restoring the matching data snapshot as well as the previous
images when schemas changed. Do not remove named data volumes as a shortcut.

## Resource and failure behavior

The agent bounds alerts, context, turns, tools and per-invocation elapsed time.
A timeout returns an error; it does not switch confidential work to an external
model. MCP startup/shutdown and I/O cleanup can add time beyond a budget boundary.
GPU contention on a shared workstation changes latency substantially.

Prometheus retains at most 14 days or 2 GB of its data. Tempo's scheduler and
worker retention flags are explicitly set to 336 hours; compacted blocks also
have their own shorter retention. Monitor disk capacity for Qdrant versions,
model artifacts, snapshots and Docker caches. Do not run global cleanup against
unrelated projects on this shared machine.

No destructive host shutdown, disk failure or long-duration load campaign is
part of the routine smoke checks. Requalify these failure modes before expanding
the workload beyond a personal workstation.
