# CI usage and runners

Inspect existing runs before dispatching another workflow. Use local validation
for iteration, batch related fixes and select hosted checks that provide missing
evidence. A successful local run is not a successful hosted run. Record the exact
commit, event, run attempt, tested scope and unresolved failures.

## Selecting checks

Application CI runs on pull requests and pushes to main, with cancellation of
superseded runs on the same ref. A branch push alone does not duplicate PR CI.
Do not rerun failed billing or deterministic test jobs until the cause changes.
For an unchanged commit with a resolved infrastructure problem, use GitHub's
failed-job rerun instead of creating another full workflow run.

Execution ceilings are 20 minutes per Python project, 10 minutes for hooks/Compose
and evaluation configuration, 15 minutes for real speech, 25 minutes for the
console and 60 minutes per image. The console ceiling allows headroom above an
observed successful 19m35 job, including browser installation. These are maximum
durations, not target execution times; investigate timeouts before rerunning.

The image workflow normally builds and scans all eight images. A direct manual
invocation can select one service after a targeted correction:

```sh
gh workflow run images-security.yml --ref main -f service=qdrant
```

Verify the resulting run's head SHA before attributing it to a correction. The
`service` choice accepts the eight inventory names or `all` (the default). The
matrix is selected from fixed literal arrays, never shell text supplied by an
operator. An unknown selection fails matrix validation. A missing selection
uses all eight images. Renaming the image workflow without updating its manual
selection guard also falls back to the complete inventory.

The weekly audit and every call from **Qualified release**, including a manual
release run, always scan all eight images. A targeted manual success does not
replace this release gate or qualify the other seven images. CRITICAL/HIGH
findings and incomplete scans still fail. Reports preserve actual image
identities, database metadata and remaining findings without suppression.

Never move a signed tag to incorporate a later fix. A failed release tag remains
failed; qualify a new candidate when the complete release is ready. Green CI
permits a draft, followed by review of functional acceptance and remaining
boundaries. It does not certify model reasoning or authorize a stable label.

## Runner decision

Keep standard GitHub-hosted runners for the current private workstation project.
The observed eight-image run on 21 October used 77.42 cumulative runner minutes,
mostly compiling Grafana, Prometheus and Tempo. This observation alone does not
justify operating an additional CI host. Actual account-wide usage, allowance,
artifact storage and queueing should inform a later decision; this is not a
claim about the owner's invoice or remaining monthly quota.

If recurring workload or hardware requirements justify self-hosting, use
dedicated disposable VMs with narrowly scoped credentials and network access.
Account for provisioning, OS updates, disk/network cost, logs and maintenance.
Start with measured demand rather than installing a fleet pre-emptively. Never
register the live platform workstation as a general-purpose CI runner or expose
its client data, SSH keys, production secrets or Docker daemon to jobs.

The current heavy-image preparation deliberately requires a GitHub-hosted runner
before deleting preinstalled SDK directories. A future self-hosted design must
replace that preparation and qualify its isolation; changing `runs-on` alone is
insufficient. No self-hosted runner is installed by this decision.

References: [rerunning jobs](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs),
[runner isolation](https://docs.github.com/en/actions/reference/security/secure-use#hardening-for-self-hosted-runners),
[billing rules](https://docs.github.com/en/billing/concepts/product-billing/github-actions).
