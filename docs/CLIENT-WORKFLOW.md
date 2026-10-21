# A client mission, from intake to handover

This guide describes the current platform, reviewed on **29 September 2026**.
It supports a trusted operator investigating an incident with local models,
reviewed runbooks and an explicit human approval step. It does not connect to
a client's infrastructure, execute remediation, provide tenant isolation or
replace the client's change-management process.

The interface offers English and French, with English selected initially and
the interface preference retained in the browser. Its language selector is
independent of AURA's conversation language. Operator evidence and model output
retain their original content. This guide uses the English interface labels;
existing CLI commands and API identifiers remain in French. Run commands below
from the deployment's checkout root. Examples use synthetic data; replace
paths and identifiers deliberately.

## 1. Agree the mission boundary

Record the client, service owner, permitted data, scope, intended deliverable,
reviewer, retention period and recovery requirements outside the platform in
the client's approved mission record. Establish who may approve a proposal
and who may execute a subsequent change in the client's environment. The
console records decisions by the local operator; it has no independent
reviewer account, role separation or client identity directory.

Use **a dedicated VM and deployment per client**, with its own OS account,
private storage, credentials, model service, databases, corpus, index,
checkpoints and backups. Qualify that VM before receiving client material.
Keep its browser access local. Do not add a public tunnel or publish its ports
as a shortcut for client collaboration.

A second checkout, a different analysis title or a different
`PLATFORM_STATE_DIR` is not tenant isolation. The console currently uses the
deployment's `runbooks/` directory, and the gateway has fixed Compose project
and container names. `RUNBOOK_DIR` alone does not relocate the console corpus.
Sharing an inference gateway, vector index or backup directory can cross the
intended client boundary. VM isolation still trusts the host and its
administrators; it is not protection from a compromised host.

| Current capability                   | Mission implication                                                                       |
| ------------------------------------ | ----------------------------------------------------------------------------------------- |
| One authenticated local operator     | Review takes place through the operator; no client portal or per-client ACLs              |
| Local analysis and embeddings        | Client material stays on the confidential model path; extraction is not declassification  |
| Bounded read-only tools              | The agent reads the local corpus; it cannot inspect a live client system or execute a fix |
| Source checks and human approval     | A verified quotation still needs applicability, prerequisites and risk review             |
| A serial analysis/maintenance worker | Schedule work; this is not a concurrent incident-response fleet                           |
| Local backups and restore drills     | Provide a separate recovery location and acceptance evidence appropriate to the mission   |

If the mission requires shared client accounts, unattended remediation,
high availability or remote access, stop at the design/qualification stage.
Those capabilities are not enabled by the current deployment.

## 2. Qualify the dedicated installation

Follow [installation](../README.md#install), [console setup](CONSOLE.md) and
[operations](OPERATIONS.md). Install the pinned dependencies and models before
loading confidential material. Downloads and updates require a separate,
reviewed network policy; “local inference” does not mean every installation
operation is offline.

Check the configured services and the actual routing boundary:

```sh
./plateforme sante
./plateforme preparation
./plateforme parametres
uv run --locked scripts/plateforme.py verifier
./plateforme voix statut
./plateforme ouvrir
```

The verifier checks service health, restricted aliases, refusal of an external
alias, model hashes, index presence and disk capacity. It does not certify
the model's answers. **Readiness** and `preparation` report the installed tools,
configuration, services and optional capabilities with explicit next steps;
see [tools and readiness](TOOLS.md). A passed operational check is not a
production certification. `voix statut` checks the installed speech capability;
voice is optional for the analysis workflow. Use the returned language and
readiness instead of assuming that an installed package supplies a working
voice. Configure a local password through `./plateforme mot-de-passe` if
needed; never pass a password or key as a command argument.

### Understand the installation before intake

Open **Architecture** from navigation or **Explore the architecture** on
**Overview**. Select **Investigation**, **Voice**, **Knowledge**, **Memory** or **Telemetry**,
then select a component to read **Role in this system**, **Data handled** and
**Boundary to remember**. **Open related workspace** takes you to the relevant
operating page. On a narrow screen, use the component list; the same controls
remain keyboard accessible.

Use this guide to explain where mission material is processed and retained.
The arrows and animation describe the design, not live traffic or an active
agent fleet. **Measured availability** is a separate set of six local endpoint
checks. **No direct health probe** means the component is not independently
measured there; it is not a successful test. Use **Check services**, **System
health** and **Readiness** to investigate the actual installation.

The interface has larger supporting text and can be zoomed with the browser.
Scrolling down and back up gives sections a brief entry accent. Motion runs
automatically; use the operating system's reduced-motion accessibility setting
for a still workspace. There is no application motion toggle. This does not change the incident
workflow or AURA's audio permissions.

Review the current [dependency findings](DEPENDENCIES.md) and
[current security assessment](SECURITY-2026-09-29.md) against the mission's
requirements. Functional health does not establish an absence of
vulnerabilities. A new machine also needs its own synthetic inference,
approval/refusal, microphone/playback if used, and backup restoration checks.
Record the application commit, pinned images, model validation results and
test date in the private mission record without copying keys.

## 3. Keep evidence private and outside development publishing

Create an operator-owned mission directory outside the checkout. For example,
in the dedicated VM:

```sh
umask 077
CLIENT_MISSION_DIR="$HOME/client-missions/synthetic-demo"
install -d -m 700 "$CLIENT_MISSION_DIR"
cat > "$CLIENT_MISSION_DIR/synthetic-alert.txt" <<'EOF'
Synthetic training incident: a demonstration PostgreSQL service reports too many clients.
No customer records, credentials or production identifiers are included.
The objective is to review a sourced investigation proposal, not to execute a change.
EOF
```

For real work, collect the smallest useful time window, symptoms, recent
changes and relevant evidence through the client's authorized process. Omit
credentials and unnecessary personal information. Keep alerts as private
UTF-8 files or protected stdin input, not shell arguments, public tickets or
screenshots. The alert limit is 20,000 characters; summarize larger evidence
with a human-reviewed reference to the protected originals.

**Never stage client material in Git.** This repository's pre-commit hook
sends staged diffs to GitGuardian. Its absence of a detected secret is not a
confidentiality guarantee. The console's runbook editor writes into the
deployment's `runbooks/` directory, which is also a versioned source location.
Use only synthetic/general procedures in a development checkout. For a
dedicated client deployment, keep customer corpus changes out of all staging,
commits, pushes and automated source-publishing workflows. An ignore rule
does not protect an already tracked file. There is currently no separate
client corpus mount setting in the console.

Raw alerts are transient input, but extracts, source excerpts, model messages,
analysis results and checkpoints can remain confidential. Protect the whole
deployment and its backups accordingly; “the original alert is not a
checkpoint field” does not mean the persisted result is anonymous.

## 4. Prepare and verify the knowledge sources

Use **Runbooks** to inspect existing documents. Have the service owner review
each procedure's scope, prerequisites, verification, rollback, owner and
review date. Each actionable paragraph must carry the conditions needed to
interpret it safely. Remove credentials and instructions intended to manipulate
the model. Treat documents as evidence to review, not trusted instructions
to the assistant.

```sh
./plateforme runbooks lister
./plateforme runbooks lire RUNBOOK_NAME.md
```

Replace `RUNBOOK_NAME.md` with an actual returned filename. To add a reviewed
document prepared privately, use **New runbook** in the UI or:

```sh
./plateforme runbooks ecrire synthetic-procedure.md --fichier "$CLIENT_MISSION_DIR/synthetic-procedure.md" --empreinte ''
```

Prepare that source file first. The empty fingerprint creates a new document.
To update an existing one, supply the exact `empreinte` returned by `lire`;
a concurrent edit is rejected instead of overwritten. Use flat `.md`
filenames containing letters, numbers, hyphens or underscores, starting with
a letter or number. Documents are limited to 8,000 characters. Symlinks and
non-regular files are refused.

Publish the reviewed corpus to the local index, then check both expected
matches and questions that should have no relevant answer:

```sh
./plateforme operation indexer --attendre
printf '%s' 'synthetic database connection limit' | ./plateforme recherche --mode texte
printf '%s' 'synthetic database connection limit' | ./plateforme recherche --mode semantique
```

The index publishes a fresh physical collection through `runbooks-current`.
Old versions remain available for controlled rollback. After a corpus change,
stale semantic results are refused until reindexing; literal search remains
available. Similarity scores measure retrieval, not operational correctness.
Preserve the reviewed source files separately: an index is not their backup.

## 5. Run one incident analysis

In **Analyses**, select **New analysis**, enter a non-sensitive title and the
alert in **Alert & context**, then select **Run analysis**. The CLI uses the
same authenticated API:

```sh
./plateforme analyses creer --titre 'Synthetic database investigation' --fichier "$CLIENT_MISSION_DIR/synthetic-alert.txt" --attendre
./plateforme analyses lister
```

Record the returned 32-character analysis ID. In the following commands,
replace `ANALYSIS_ID` with that ID:

```sh
./plateforme analyses voir ANALYSIS_ID
./plateforme analyses attendre ANALYSIS_ID --delai 300
```

Waiting stops at a stable state, including **Awaiting approval**. A CLI wait
deadline or interrupt does not cancel a submitted job. To stop queued or
active work explicitly, use `./plateforme analyses annuler ANALYSIS_ID`.
Inspect the returned `statut`; an exit code of zero can mean a successful
status request, not a completed, approved diagnosis. Do not automatically
retry an incident under its previous ID.

### Read progress without overinterpreting the charts

Return to **Overview** for the saved-run and service indicators. Under
**Created runs**, switch between **7 days** and **14 days**. Use **Inspect a day**
with the keyboard, or expand **View chart data**, to read the exact count and
UTC date. **Run states** describes all currently retained records, regardless
of the selected activity period; **Service response** describes current probes.

These records include maintenance operations as well as analyses. Completion
does not establish diagnosis quality or client acceptance. Deleting a record or
applying retention changes the chart, so preserve the required mission evidence
in the private mission record. Check the displayed refresh time before relying
on service status. Probe durations do not measure model-response time or a
historical availability commitment. Use **Observability** for detailed metrics
and traces, and the individual analysis for evidence and the approval decision.

### Optional conversation with AURA

The **Voice assistant** provides optional local conversation through AURA.
**Record** puts recognized speech into an editable draft for review before
sending. **Start conversation** explicitly enables hands-free mode: after a
speech pause, it sends the transcription, reads the reply and listens again,
for up to 20 turns. Use **End conversation** or Escape to stop. Choose manual
recording when every transcript needs review before submission. Check displayed
answers before sharing them. A spoken “yes” does not approve a proposal.
Conversation is saved locally with bounded recent context and has no execution or approval authority;
important evidence belongs in the mission record and the supervised analysis
workflow. If audio is unavailable, use typed input rather than a cloud speech
fallback.

## 6. Review the proposal and make an explicit decision

Open the analysis or **Approvals**. Check the exact source passage and
fingerprint, the observed incident, missing evidence, prerequisites, expected
effects, rollback and any reported instruction injection. The source guard
checks provenance of complete passages actually read. It does not establish
that a quoted procedure is safe for this service now.

If the proposal is justified, select **Approve proposal**, or run:

```sh
./plateforme analyses approuver ANALYSIS_ID --attendre
```

If the evidence or applicability is insufficient, choose **Reject proposal**
instead:

```sh
./plateforme analyses refuser ANALYSIS_ID --attendre
```

These are alternative decisions, not a sequence to execute. Concurrent or
repeated decisions are rejected. A pending or rejected analysis has no
delivered diagnosis. Correct the evidence or corpus and start a new analysis
when necessary. Approval releases a diagnosis; it does not run its commands
or authorize a change under the client's process. Never pipe generated text
into a shell.

If a change is subsequently approved by the client, its authorized operator
executes it through the client's own tools and records the outcome there.
Bring the resulting evidence back as a new analysis when another assessment
is needed.

## 7. Export and review the deliverable

Export the selected result to a new private file:

```sh
./plateforme analyses exporter ANALYSIS_ID --format md --sortie "$CLIENT_MISSION_DIR/reviewed-report.md"
./plateforme analyses exporter ANALYSIS_ID --format json --sortie "$CLIENT_MISSION_DIR/reviewed-report.json"
```

The exporter creates mode-0600 files and refuses to overwrite an existing
file. Export is not a redaction or approval step; verify the actual status
and contents. A browser download has the browser's download-directory
permissions and its own retention.

Prepare a client-facing handover containing the incident scope, observation
period, reviewed evidence, source names/fingerprints, accepted conclusion,
uncertainties, human decision, proposed next steps and any separately recorded
execution/verification outcome. Remove internal identifiers, unrelated
customer material and sensitive operational details that the recipient does
not need. An analysis export is not a complete mission archive or an
immutable audit certificate.

Transfer the reviewed deliverable using the client's approved channel. The
platform does not provide a client-sharing portal or automatically send
reports to external recipients.

## 8. Back up and exercise recovery

Schedule maintenance when the mission can tolerate it; backup operations
share the serial worker with analyses. Run a backup and its restore drill:

```sh
./plateforme operation sauvegarder --attendre
./plateforme operation tester-restauration --attendre
```

The operation tests the most recent eligible local backup. To identify and
test an exact backup directly, use:

```sh
uv run --locked scripts/sauvegarder.py
uv run --locked scripts/tester_restauration.py /path/returned/by/the/backup
```

Backups live under `~/.local/state/platform-backups/` and contain secrets.
Require `complet=true` in their manifest. Keep an additional protected copy
in the client-approved recovery location; a second directory on the same VM
does not protect against loss of that VM. Encryption and off-host transfer
must be supplied by the deployment's storage/recovery process.

| Included in the current platform backup         | Preserve separately                                 |
| ----------------------------------------------- | --------------------------------------------------- |
| Private environment and gateway configuration   | Reviewed Markdown runbook source files              |
| PostgreSQL archive                              | Original evidence and handover exports              |
| Console state and graph checkpoints             | Model artifacts and installation/rebuild evidence   |
| Grafana SQLite and active Qdrant index snapshot | Tempo/Prometheus history if the mission requires it |

Sessions and login tickets are removed from the backed-up console state.
Individual database copies are coherent, but the set is **not atomic across
databases**. For a coordinated mission checkpoint, pause incoming work and
other writers before taking it. A restore drill uses disposable resources;
it does not replace the live installation or prove production role/grant
restoration, every dashboard migration, or a recovery-time commitment.
Follow [recovery procedures](OPERATIONS.md#console-recovery) for an actual
recovery, then inspect interrupted and pending work before resuming.

## 9. Close the mission and apply retention

Before closure, resolve or explicitly cancel active jobs, capture the reviewed
deliverable and recovery evidence, and agree the disposition of each data
copy with the client. Delete an inactive analysis explicitly when appropriate:

```sh
./plateforme analyses supprimer ANALYSIS_ID --confirmer
```

That removes its console record and checkpoint, not its exports, runbook
sources, index versions, screenshots, backups or VM snapshots. Console
analyses, including pending approvals, expire after 14 days without activity;
active jobs are excluded. Audit events and editor revisions have a 30-day
limit. Separate daily timers remove inactive standalone graph state and
eligible local backups after 14 days. Host downtime can delay cleanup.

```sh
uv run --locked scripts/plateforme.py installer-retention
systemctl --user list-timers platform-backup.timer sre-agent-retention.timer
```

These defaults are not a client-configurable retention policy in the UI.
If the agreed mission period differs, resolve that requirement before intake.
Retain necessary approved evidence in the separate, governed mission archive.
Logical deletion is not certified secure erasure of storage snapshots or
physical media. Decommission the dedicated VM and all approved recovery
copies through the client's storage process; do not relabel an existing
client deployment and reuse its retained data for another client.

## Workstation tool audit for this guide

Read-only checks on 27 September 2026 found Git 2.43.0, uv 0.12.5,
Node 22.22.0 (the system version at that audit), npm 11.10.0, Docker 29.2.1
and Compose 5.1.0, plus ripgrep,
direnv, curl, jq and OpenSSL. The control API, agent and runbook environments
use Python 3.14.7; speech uses Python 3.13.15. The system Python is 3.12.3
and must not be substituted for those locked environments. In this shell,
uv is at `~/.local/bin/uv` rather than on `PATH`; the `./plateforme` wrapper
handles that location. Add that directory to the operator's `PATH` before
using the standalone `uv` commands above.

Playwright's Chromium installation is present. The MCP configuration declares
the runbook server and the read-only control adapter. Their presence is not a
test of a connected MCP client. The authenticated health check reported all
six configured services healthy and an index of 31 points. The bare Ollama
CLI's default endpoint was unavailable, while the configured inference
endpoint passed the platform check; use the configured check when diagnosing
this deployment.

Standalone `ffmpeg`, `sox` and `neo4j` were not found on `PATH`. They are not
required by the current workflow: local speech uses PyAV, and durable incident
state/retrieval use SQLite and Qdrant. This inventory is evidence about this
workstation on this date, not a guarantee that a newly provisioned client VM
is ready or that additional packages would improve the security boundary.
Use the current [installation requirements](../README.md#install) when preparing
a deployment; this dated inventory is not a pin for later maintenance releases.
