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
**Readiness** page. Its 20 checks cover local permissions/listeners, installed
runtimes, six services, restricted alias inventory, knowledge, both voices,
actual handshakes with the two MCP servers and a synthetic document-sandbox
extraction. It has no automatic repair, downloads
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

The [24 October qualification](QUALIFICATION-2026-10-24.md) separates source
publication, local proofs and release acceptance. The corrected eight-image scan
against the 24 October 13:07:23 UTC database reports 0 CRITICAL, 0 HIGH,
24 MEDIUM, 9 LOW and 6 UNKNOWN occurrences. It follows an initial failure with
nine HIGH occurrences. See [ADR 0055](adr/0055-dependances-corrigees-et-contrat-filelock.md)
for the actual fixed packages and the explicitly tested local filelock contract.
The OTel source backport retains its truthful raw inventory finding and provenance.

The [installed checkpoint](QUALIFICATION-2026-10-24.md#installed-workstation-and-hosted-gates)
records signed main `05937ab4d19e`, sixteen hosted jobs, restored-backup checks and
post-installation FR/EN real speech/GPU tests. Its verified rollback material stays
private on the reference host. This same-host evidence does not replace an
encrypted recovery copy and key held independently of that workstation. Public
source does not expose the local services. The earlier dated reports retain their original counts and failed
runs. A stopped release tag is never moved or relabelled as a success after a
later correction. The host certificate store needs separate
[administrative verification](HOST-TOOLS.md#host-certificate-trust-and-uv).

The [23 October reference-host incident](HOST-INCIDENT-2026-10-23.md) is resolved
at the 24 October checkpoint after the operator's Windows/WSL update and reboot.
Linux GPU telemetry and actual local generation pass. The full gateway qualifier
passes streaming, structured output, embeddings, real trace delivery, restart and
logical rollback. Do not substitute an embeddings-only diagnostic for that full
profile. Cold model loading still takes materially longer than a warm turn.

Seven image derivatives changed in the broader campaign; Tempo's local identity
is retained. The 24 October update changes Grafana, LiteLLM and Qdrant, whose
current tag is `1.19.2-security.20261024.1`. The dated qualification records
the exact local identities. Its functional runtime checks used Docker's
default seccomp; a separate upstream io_uring test profile is not a deployment
setting. Its measured Docker build took 14 minutes 52.8 seconds with an 8.8203 GiB
Rust compiler cgroup peak, including file cache and with unchanged stages cached.
Reserve the documented build resources and preserve a recoverable previous data
generation before updating services. See [compatible image fixes](adr/0052-correctifs-images-compatibles.md).

The manual/weekly [image security workflow](../.github/workflows/images-security.yml)
builds and scans eight images in independent jobs: the six core services, the
monitoring exporter and dedicated Neo4j memory. It retains reports and fails for
any HIGH/CRITICAL occurrence or incomplete scan. The [release workflow](../.github/workflows/release.yml)
reuses both image and functional checks; a version tag can create a draft only
after both pass. It does not publish automatically. A completed functional CI
run alone is not an image-security sign-off.

For deliberate CI usage, targeted manual image audits and the current runner
decision, see [CI operations](CI.md). Scheduled and release audits retain the
complete eight-image inventory.

The provisioned data sources use `Plateforme Tempo` and `Plateforme Prometheus`
with stable UIDs. Older sources named `Tempo` and `Prometheus` remain available
so their generated UIDs and existing dashboards are preserved during upgrades.

## Operational dashboards

See [Monitoring](MONITORING.md) for the six bilingual Grafana views (twelve dashboards),
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

New backups also include the active Markdown runbook corpus, console missions,
conversation messages and attachments, durable graph state and dedicated Neo4j
memory when configured. Additional mission files, reports and exports require
explicit private roots in `PLATFORM_BACKUP_INCLUDE_DIRS`; arbitrary filesystem
content is not discovered automatically. Each data file has a checked size and
SHA-256 inventory. Browser sessions and one-use tickets are excluded.
See [RECOVERY.md](RECOVERY.md) for the exact inventory, isolated synthetic
roundtrip, age export and restore/rollback instructions. An encrypted local
export is not evidence of an independently protected off-host copy.
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
Install the [host prerequisites](HOST-TOOLS.md) and run `./plateforme prerequis`
first. The real document-isolation probe is mandatory both during installation
and inside the service at startup. Console and backup units use an explicit
PATH including `~/.local/bin` for qualified private bubblewrap/age installations.
Use `systemctl --user status ambicrafted-console.service` and
`journalctl --user -u ambicrafted-console.service` for lifecycle diagnostics;
HTTP access logging is disabled. The API binds only to `127.0.0.1:8787`.
See [CONSOLE.md](CONSOLE.md) for the operator commands and private login flow.

On the reference workstation, user lingering was enabled and verified as
`Linger=yes` on 2026-10-20. This permits the user manager and timers to remain
active after logout; it does not keep Windows or WSL running, wake a powered-off
machine, or prove recovery after reboot. No Windows/WSL restart was simulated
during this qualification. On another host, have its administrator review
`loginctl enable-linger USER` and verify the user manager, services and timers.
No external alert recipient is configured and no desktop delivery tool is
available on the reference host. Selecting a destination and proving actual
alert delivery remain operator actions; a visible dashboard is not delivery.

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

## Document generation diagnostics

For a failed diagram/report, inspect the NDJSON `error.code` and correlate its
request `operation_id` with the `plateforme.documents` warning in the private
console service journal. The structured message contains only `category` and
`operation_id`; no prompt, source, response body, raw exception, traceback or
credential is logged. Keep access to the journal private. Existing text-dialogue
errors retain their original response shape.

| Code | Established boundary and next check |
| --- | --- |
| `document_output_invalid` | Generation returned an invalid/incomplete/bounded output, envelope or artifact schema. Inspect the request complexity and supplied information; do not treat a discarded draft as saved. |
| `document_review_invalid` | Exhaustive review could not be completed within its input bounds, or its response was invalid, unfinished, missing references or contained duplicate/unknown references. No positive review is inferred. |
| `document_review_rejected` | A valid, complete review returned at least one non-retain verdict. Review the source/request; this fallible reviewer may also reject a useful draft. |
| `document_timeout` | A typed request/deadline timeout occurred. Check local model/gateway load before a deliberate retry; no automatic retry was added. |
| `document_upstream` | HTTP/transport failed during either call. Check local gateway availability/authentication privately; this category does not expose or infer its response body. |
| `document_storage` | Saving the completed turn failed or was refused, including a missing conversation, quota or SQLite failure. Check history and storage before retrying an uncertain operation. |
| `document_unknown` | The caught failure does not establish a narrower category. Do not guess from the generic public message. |

Prompts, acceptance rules, schemas, call budgets and atomic persistence are
unchanged. Cancellation remains cancellation. A successful generation/review
still does not establish factual correctness or expert model quality.

The two original unpublished postpromotion attempts did not retain these categories, so
their cause remains undetermined. Two separately authorized synthetic diagnostic
attempts later observed one direction-based review rejection and one accepted
report. The accepted report overstated uncaptured logs as unavailable; it is not
a semantic success. These new attempts cannot establish the original causes.
Raw diagnostic captures stay private and are not part of routine logging.

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
For a reversible local promotion, stop writers and copy the offline volumes to
new names, retaining the originals. The [recovery volume selectors](RECOVERY.md#select-preserved-or-recovered-volumes)
keep the normal CLI and Compose commands usable after selection; unset variables
retain existing names. Validate that selected volumes already contain the
intended state before starting services. A successful `config --quiet` checks
configuration syntax, not the presence or integrity of data.

```sh
uv run --locked scripts/securiser_services.py
cd gateway
docker compose config --quiet
docker compose up -d --build --wait --wait-timeout 180
```

The service provisioner requires `htpasswd` from `apache2-utils`. It creates
independent Qdrant write/read keys and a Prometheus password without displaying
them; existing credentials must agree between the two private environments.
When upgrading an existing installation, stop the console, agents and scheduled
writers before provisioning and restarting the affected services. Preserve a
verified backup and the previous configuration first. Regenerate the mounts
after restoring `workspace.env` and `gateway.env`, then recreate Qdrant,
Prometheus, Tempo and Grafana. Do not rotate credentials by editing one copy.

For the isolated native-authentication acceptance test (no live data or host
ports), with the candidate images already built:

```sh
uv run --locked scripts/qualifier_frontiere_services.py /private/new-service-auth-evidence
```

The output directory must be new. Its receipt records anonymous and wrong-key
refusals, read-only write denial, authenticated search/snapshot restoration,
five scrape targets, Grafana backend queries, Tempo remote-write and restart
persistence. A failure does not authorize installation; retain its evidence.

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
