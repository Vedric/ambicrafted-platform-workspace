# Personal production recovery

The supported scope is a private, single-operator Linux installation. Recovery is
**staged into new files and disposable services**. None of the commands below
replaces a live database automatically. A successful local restore is not proof
that the workstation can be lost safely: keep an encrypted copy and the recovery
identity outside the workstation, and test on the replacement environment.

Initial objectives: **RPO ≤ 24 hours, RTO ≤ 2 hours**. These are targets, not
measured guarantees. Record the last usable backup time, exercise start/end,
validated services and exceptions in the release evidence.

## Backup contract

Run from the installed workspace, whose root/gateway `.env` belong to the target
installation. Do not run an operational backup from an unrelated checkout.

```sh
uv run --locked scripts/sauvegarder.py
uv run --locked scripts/tester_restauration.py /absolute/path/to/backup
```

New backups contain a SHA-256/size inventory of every data file. The restore drill
checks the inventory **before** starting Docker. Missing, extra, modified and
unsafe files fail verification. The manifest records the repository revision,
whether its working tree was clean, the source roots, exclusions and lack of
atomicity across services. The manifest is private too; do not publish it.

| Data | Included | Recovery constraint |
|---|---|---|
| Root/gateway configuration and secrets | Existing `.env` and Compose/config files | Local copy is confidential plaintext; off-host copy must be encrypted. |
| Console missions, audit, revisions | Consistent SQLite backup | Read through the application after restoring. |
| Conversations and extracted attachments | Same SQLite backup, explicit row counts | Original uploads discarded by the application are not recreated. |
| Per-mission and CLI graph checkpoints | SQLite backups | Validate the delivery contract; never force-resume an obsolete approval. |
| Browser sessions and one-time login tickets | **Excluded before writing backup** | Authenticate again; do not reconnect restored credentials. |
| Dedicated Neo4j notes and relationships | Bounded logical snapshot | Rebuild the uniqueness constraint; validate complete graph content. |
| Active Markdown corpus | `RUNBOOK_DIR`, default `runbooks/` | Same top-level, non-hidden `.md` selection and limits as the MCP. |
| Additional mission files/exports | Explicit configured roots only | See configuration below. No automatic scan of the home directory. |
| Active Qdrant index and alias inventory | Collection snapshot(s) | Restore aliases and compare corpus fingerprint; reindex on mismatch. |
| LiteLLM PostgreSQL | Custom-format database dump | The drill omits ownership/grants: verify production roles separately. |
| Grafana | Consistent SQLite database | Reinstall provisioned configuration from the recorded revision; check dashboards/plugins. |
| Prometheus/Tempo historical samples | **Excluded** | Preserve their volumes separately if historical retention matters. |
| Model weights and transient audio | **Excluded** | Reinstall pinned weights; do not promise offline recovery without a model cache. |

Private additional source roots can be configured in the root `.env`; use an
absolute path for each directory. This example contains no credentials:

```dotenv
PLATFORM_BACKUP_INCLUDE_DIRS='["/home/operator/private-missions"]'
```

The backup copies regular files recursively from these roots, including hidden
files; review the roots deliberately. Symlinks, special files, group/world-writable
sources, overlapping backup/source directories and exceeded limits fail closed.
Do not include the recovery private key or an entire home directory. Bounds:
16 additional roots, 256 MiB per additional file, 20,000 data files, 8 GiB total.
The indexed corpus retains its 1,000-entry/200,000-byte-per-file limit. Exceeding
a limit is an incomplete backup, never silent truncation.

SQLite snapshots are individually consistent. PostgreSQL, Qdrant, Neo4j and
files are captured at different instants. **For a continuity backup before an
upgrade, stop new work and all writers, including CLI/indexing processes.** Stop
the console service after current jobs finish. Leave database services running
so their supported snapshot APIs work. Resume the console only after backup and
drill succeed. Do not claim a distributed atomic snapshot.

## Encrypted export with age

The qualified CLI version is **age v1.3.1** (`age` and `age-keygen` on PATH).
Use the repository's [verified host-tool installer](HOST-TOOLS.md) or install
that pinned release from the [official project](https://github.com/FiloSottile/age/releases/tag/v1.3.1)
after verifying its release checksum/signature. The repository installer pins
official Linux amd64/ARM64 archive hashes and preserves existing foreign tools.

Generate and keep the private identity on the recovery system or a separately
protected recovery medium. `age-keygen -o` writes the secret directly to its file;
never print the identity. Only the public recipient file belongs on the platform.

```sh
umask 077
mkdir -p "$HOME/.config/ambicrafted-recovery"
age-keygen -o "$HOME/.config/ambicrafted-recovery/identity.txt"
age-keygen -y "$HOME/.config/ambicrafted-recovery/identity.txt" > "$HOME/.config/ambicrafted-recovery/recipients.txt"
```

Back up the private identity independently, and verify it decrypts a sample
before depending on it. Creating the key beside the backup and leaving both on
the same disk does not meet the recovery objective. The public recipient alone
cannot recover data. Loss of the private identity means loss of the encrypted
copy. No private recovery identity is generated or committed by the repository.

Prepare an existing private export directory, then export a **new-format** backup:

```sh
install -d -m 700 "$HOME/.local/state/platform-encrypted-exports"
uv run --no-project --python 3.14 python scripts/exporter_sauvegarde.py encrypt \
  /absolute/path/to/backup \
  --recipients "$HOME/.config/ambicrafted-recovery/recipients.txt" \
  --output "$HOME/.local/state/platform-encrypted-exports/backup.tar.age"
```

This verifies the inventory, creates a private temporary plain archive, encrypts
it, removes the temporary archive and prints only aggregate results, the encrypted
path and ciphertext hash. It refuses existing output, excludes plugins/SSH
recipients, and does not print secret material or encryption diagnostics. Plain
staging uses disk space and is removed normally; this is not secure SSD erasure.
Use encrypted storage for the workstation and recovery system.

The export hashes the bytes actually consumed by the tar writer against the
validated inventory; changing a source and restoring it between two checks
cannot silently produce a successful inconsistent export. The manifest archived
is the already validated in-memory copy. The recovery identity remains a trusted
operator file: permissions are checked before age opens it by pathname.
Concurrent replacement by another process running as the same operator is
outside this single-user boundary; use an identity on a protected recovery
system and do not run untrusted same-user processes during recovery.

Copy the `.tar.age` to your independently protected destination using the chosen
storage tool. Compare the reported ciphertext SHA-256 after transfer and retain
it in your recovery evidence. **Encryption does not prove transfer, off-host
placement, author identity or recoverability.** The script explicitly reports
`copie_hors_poste_verifiee=false`; it does not guess a remote account or destination.

The daily backup can stage an encrypted export automatically after its local
snapshot completes. Configure **both** settings in the root `.env`:

```dotenv
PLATFORM_BACKUP_AGE_RECIPIENTS_FILE=/home/operator/.config/ambicrafted-recovery/recipients.txt
PLATFORM_BACKUP_EXPORT_DIR=/home/operator/.local/state/platform-encrypted-exports
```

The export directory must already exist with private permissions. An encryption
or destination failure makes the scheduled command fail; the completed local
snapshot is retained. A missing setting fails rather than silently falling back
to plaintext export. The existing 14-day local retention does **not** prune the
export destination. Configure retention in the selected backup/storage system.
If using a mounted off-host filesystem, monitor the mount itself: a writable
local mountpoint alone does not prove the remote storage is mounted.

## Recover into a new environment

1. Retrieve the encrypted archive, independently protected identity and recorded
   code revision. Install the pinned tools and dependencies for that revision.
   Do not expose the service publicly during recovery.
2. Create a private parent directory and decrypt to a **nonexistent child**:

   ```sh
   install -d -m 700 "$HOME/recovery"
   uv run --no-project --python 3.14 python scripts/exporter_sauvegarde.py restore \
     /absolute/path/to/backup.tar.age \
     --identity /absolute/path/to/identity.txt \
     --output "$HOME/recovery/restored-backup"
   uv run --locked scripts/tester_restauration.py "$HOME/recovery/restored-backup"
   ```

   The entire age payload is authenticated before extraction. The extractor
   accepts only bounded USTAR regular files, rejecting traversal, duplicates,
   symlinks, devices and extended metadata. It validates the manifest/inventory
   before publishing the new directory. Incorrect keys or tampering leave no
   published restore. USTAR path constraints apply (name/prefix fields); export
   fails for unrepresentable paths rather than shortening them.
3. Restore the private configuration to the **new** installation, adjusting only
   host-dependent paths. Restore source roots using the manifest mapping; remap
   `RUNBOOK_DIR` and explicit mission roots. Apply 0700 directories and 0600 files.
   Do not print or paste `.env` contents into a terminal/transcript.
4. Restore each service into fresh volumes/databases. Restore PostgreSQL with the
   matching major version and intended owner, then check roles/grants. Restore
   Qdrant snapshots and aliases and validate or rebuild the runbook index. Import
   Neo4j notes/relationships through the dedicated graph recovery procedure used
   in `memoire_sauvegarde.restore_check`, preserving its uniqueness constraint.
   Copy console/Grafana SQLite snapshots only while their writers are stopped.
   Do not overlay a newer schema on an older running service.
5. Start the control plane once. Queued/running jobs become interrupted; pending
   approvals require explicit inspection. Check the mission report, source
   citations, conversation, document and graph relationships. Authenticate again,
   run `./plateforme verifier`, check UI/CLI and dashboards, then run the isolated
   synthetic exercise below. Rotate/revoke credentials after loss or suspected
   compromise of the original host.
6. Record elapsed time, recovered generation, count comparisons and all failures.
   Keep the original backup and old volumes unchanged until acceptance. Off-host
   recovery is qualified only after this exercise actually succeeds there.

The automated tools cover verification, encrypted staging and disposable database
restoration. They intentionally do not provide an unattended command that copies
secrets into a live installation or overwrites live databases.

## Nonempty recovery qualification

Run the application-state/age exercise in the control API's locked environment:

```sh
uv sync --project apps/control-api --locked --all-extras
uv run --project apps/control-api --no-sync python scripts/exercer_recuperation.py
```

For a real disposable Neo4j restore, add `--neo4j-image` with the exact pinned,
locally available image from `gateway/neo4j-memory.yml`. This creates only a unique
synthetic container and removes it afterward. The exercise never accesses the
live graph. A run without this option explicitly reports `neo4j_restaure=false`.

The fixture includes one stored mission/report, an actual LangGraph checkpoint,
a conversation with two messages, one extracted CSV attachment, two graph notes
and one relationship. It encrypts/decrypts the backup, reopens the state through
the production repositories, reads the graph checkpoint and verifies that session
and login-ticket markers never reached a backup file. It does not call a model,
execute a remediation or claim to measure agent diagnostic quality.

On 2026-10-20 the actual age round trip and disposable Neo4j check succeeded on
the engineering workstation. Separate tests exercise corrupted archives, wrong
keys, path traversal, links/FIFOs, altered inventories, omitted content, orphans
and non-overwrite guarantees. The operational PostgreSQL/Qdrant restore drill
remains a separate check on the actual backup generation.

## Upgrade, rollback and fault handling

Before upgrading: finish or cancel active work, stop writers, take a continuity
backup, export it, run the restore drill, and record code revision, image digests
and dependency locks. Preserve existing volumes; do not prune them as part of an
upgrade. Run the candidate in an isolated environment with synthetic data first.

After upgrading: validate confidential routing, UI/CLI authentication, a complete
mission, AURA text/audio, conversations, documents, sources, graph memory and
monitoring. A failed check blocks acceptance.

For rollback, stop candidate writers and keep a separate copy of their data.
Restore the **previous code/images together with their pre-upgrade backup** into
fresh volumes, then repeat the checks. Reverting only the Git checkout is unsafe
when a dependency or schema migration changed stored data. Changes made after
the backup may be lost; reconcile them explicitly. No cross-version migration or
RTO is certified solely by this procedure.

Common failed checks: private permissions/ownership, wrong age version or key,
changed source during backup, source/index mismatch, full staging storage,
incomplete manifest or an unavailable Docker image. Do not disable verification
or dump client files to diagnose them. Reproduce with the synthetic exercise,
then inspect only aggregate status and private local logs under the operator's
control. A legacy backup without the new inventory remains drill-readable but is
reported `integrite_verifiee=false` and cannot be exported as a qualified new
archive; create a new backup instead.

References: [age CLI](https://github.com/FiloSottile/age/blob/main/README.md),
[LangGraph checkpoint state](https://docs.langchain.com/oss/python/langgraph/checkpointers).
