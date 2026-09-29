# Operations

Run commands from the checkout root unless another directory is shown. Never
print `.env`, resolved Compose configuration, response bodies containing keys,
or container environments. Scripts below keep credential values out of output.

## Daily checks

```sh
./plateforme preparation
./plateforme statut
uv run --locked scripts/plateforme.py verifier
docker compose --project-directory gateway ps
```

`preparation` (also `doctor`) reads the same measured checklist as the UI's
**Readiness** page. Its 19 checks cover local permissions/listeners, installed
runtimes, six services, restricted alias inventory, knowledge, both voices and
actual handshakes with the two MCP servers. It has no automatic repair, downloads
or inference requests. Results are cached for 30 seconds and voice artifacts for
up to 60 seconds. Required failures produce CLI exit code 2; voice and monitoring
are optional. Review the evidence, not only the summary. See [TOOLS.md](TOOLS.md)
for the exact contract and remaining qualification limits.

The separate `scripts/plateforme.py verifier` reports health, restricted aliases, refusal of an external
alias, model digests, index presence and free disk space. It uses synthetic
content for the routing refusal probe. It does not measure model correctness.
Tempo readiness and exporter errors are also visible through local Prometheus
metrics and the provisioned Grafana dashboard `plateforme-sre`.

The dashboard and rules are versioned under `gateway/observability`. Rules
create local alerts; no Slack, email or other notification destination is
configured. Configure a destination only after deciding what metadata may leave.

The [security assessment dated 26 September 2026](SECURITY-RELEASE-2026-09-26.md)
records 166 remaining HIGH package occurrences in the promoted image set. Its
conditional GO is limited to the existing supervised private workstation.
Unqualified production security approval and remote/untrusted multi-user access
remain NO-GO. Re-run scans and review reachability, ownership and remediation
before changing that decision; a green readiness page does not supersede it.

The manual/weekly [image security workflow](../.github/workflows/images-security.yml) scans all six pinned images,
retains reports and fails for HIGH/CRITICAL findings. It is separate from the push
functional workflow so residual image debt remains visible. [The scanner and
dated assessment](SECURITY-RELEASE-2026-09-26.md) describe the baseline evidence;
a completed functional CI run is not an image-security sign-off.

The provisioned data sources use `Plateforme Tempo` and `Plateforme Prometheus`
with stable UIDs. Older sources named `Tempo` and `Prometheus` remain available
so their generated UIDs and existing dashboards are preserved during upgrades.

## Operational dashboards

See [Monitoring](MONITORING.md) for the three bilingual Grafana dashboards,
`./plateforme observabilite installer`, freshness rules and local alert recovery.
The exporter has no host port or credential mount. The existing
`./plateforme observabilite` summary remains compatible; `collecter` explicitly
refreshes the aggregate snapshot. User-systemd schedules the collector.

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

The platform backup does not copy the Markdown corpus or an operator's separate
mission files, reports or exports. Preserve those through a private client backup
process, without committing client material to this development repository.
Transient audio and downloadable voice-model weights are excluded; reinstall
voice weights from the pinned manifest after recovering the private state.

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

The UI language preference is browser-local, defaults to English, and can be
changed to French independently of AURA's conversation language. It is not part
of the console database backup. Mission presets only open editable SRE briefs;
review the filled evidence before submission. They neither provision a client
workspace nor establish an access boundary. Use the
[client mission guide](CLIENT-WORKFLOW.md) for dedicated client environments,
evidence handling, approvals, export and cleanup.

On restart, queued, executing and decision-in-progress jobs become interrupted;
the server never silently replays an alert. Pending human approvals remain
available. Cancel or explicitly resubmit interrupted work after verifying what
happened. Only one control process can own a state directory.

Backups include a sanitized console SQLite snapshot and individual graph
checkpoints, including saved conversations and extracted attachments. If dedicated
Neo4j memory is configured, its bounded logical notes/relationships are also included
and verified in a disposable authenticated Neo4j instance during restore testing.
See [MEMORY.md](MEMORY.md) for its scope and read-committed consistency limits.
Sessions and login tickets are removed in memory before writing the
snapshot. Each database snapshot is coherent, including committed WAL data, but
the collection is **not atomic across databases**. Inspect interrupted and pending
jobs after a disaster recovery. Restoring the console while writers are running
is not supported. Stop the service, keep a private copy of the current state,
restore into a new private state directory, then restart and inspect it. Never
reuse the previous `-wal`, `-shm` or journal files beside a restored database.
Reconfigure the state path or replace the stopped directory as a whole, keeping
the old private directory for rollback. Authenticate again after recovery.
The restoration test checks copies only; it does not activate restored data.

## Voice and MCP diagnostics

```sh
./plateforme voix statut --langue en
./plateforme voix statut --langue fr
./plateforme preparation
```

If an optional voice check fails, follow [VOICE.md](VOICE.md) to synchronize the
locked speech environment and explicitly install/verify its model files in the
correct private state directory. A green artifact check does not test the actual
microphone, browser permission, accent or playback device. Qualify those with
synthetic speech before receiving client material.

AURA's manual recording mode permits transcript review. Explicit conversation
mode alternates capture, local transcription, dialogue and playback. It stops on
Escape, a hidden tab, route departure, 12 seconds without detected speech or
20 completed turns. Silence after detected speech ends a turn after approximately
1.1 seconds, with a 30-second cap per spoken turn. Manual recordings retain the
90-second cap. Before hands-free mode, AURA warms the local model with fixed
synthetic input; preparation can be retried if the gateway is unavailable or busy.
No microphone data is collected during preparation. Conversational STT/TTS have
30-second browser deadlines; generation has 45 seconds. Disconnecting cancels
the STT/TTS subprocess and releases its lock. Error recovery preserves written
messages/replies where available. This is not simultaneous streaming or permission
to act. On a noisy
microphone, stop the conversation and use an editable manual recording instead.

The `.mcp.json` configuration has one NEXUS stdio entrypoint. Run the MCP client from this
checkout with `uv` on its `PATH`, and start the control API first. Readiness tests
actual startup and tool inventories through its two profiles: four runbook tools
and eleven control tools. The control backend reads the local API with its private credential;
missing configuration returns unavailable without initialization. Never paste a
key into a tool configuration or connect confidential source tools to an external
consumer. [TOOLS.md](TOOLS.md) documents the bounded read-only surface; there is
no generic shell, network, approval or remediation MCP capability.

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

For a console/API update, synchronize the locked Python projects, rebuild the
console with `npm ci` and `npm run build`, run the exact-commit checks, then restart
`ambicrafted-console.service`. Reinstall its unit with
`./plateforme installer-service --remplacer` when its checkout or settings change.
Run readiness and synthetic UI/CLI checks after the restart, including the chosen
interface language, AURA if used, and an explicit approval/refusal. Do not infer
successful deployment merely because a build completed.

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
