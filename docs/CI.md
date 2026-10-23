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

The browser job retains one diagnostic retry in CI and fails if any test is
flaky. A passing retry does not satisfy the gate. Inspect the retained trace,
correct the established cause and validate locally before pushing the change;
do not hide uncaught browser errors or repeatedly rerun an unchanged candidate.

Execution ceilings are 20 minutes per Python project, 10 minutes for hooks/Compose
and evaluation configuration, 15 minutes for real speech, 25 minutes for the
console and 60 minutes per image. The console ceiling allows headroom above an
observed successful 19m35 job, including browser installation. These are maximum
durations, not target execution times; investigate timeouts before rerunning.

On 23 October, two console jobs exhausted that ceiling while APT was still
downloading Playwright's system dependencies from the Ubuntu Azure mirror. No
browser tests started in those attempts. The logs establish slow acquisition,
not whether the mirror backend or the runner's network path caused it.

Before its first APT operation, the console job now runs a guarded preparation
for GitHub-hosted Ubuntu 24.04 only. It validates the
[official runner mirror layout](https://github.com/actions/runner-images/blob/ubuntu24/20261012.334/images/ubuntu/scripts/build/configure-apt-sources.sh),
prefers the existing HTTPS Ubuntu archive and security mirrors, and retains
Azure as the final fallback. An unexpected layout fails before privileged writes.
APT HTTP/HTTPS connection and inactivity timeouts are 30 seconds; this is not a
total download deadline and does not detect a continuously slow transfer. See
[APT mirror priorities](https://manpages.debian.org/trixie/apt/apt-transport-mirror.1.en.html)
and [transport timeouts](https://manpages.debian.org/trixie/apt/apt-transport-http.1.en.html).
The helper preserves Ubuntu sources, suites, components, signing keys and
[APT package verification](https://documentation.ubuntu.com/security/software-integrity/archive-verification/).
Each file is replaced atomically. The two files are not a single transaction;
any failure stops the disposable job before package installation. The helper
installs no packages itself. Local fixture tests cover refusals and unchanged
trust settings; only a subsequent hosted run can establish download performance
and complete browser acceptance. The 25-minute job ceiling and all test gates
remain unchanged. This preparation must not be run on a personal workstation or
a self-hosted runner.

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

Image preparation remains bounded to 30 minutes except the Qdrant Rust source
build, which has 45 minutes; scanning keeps its separate 11-minute outer bound
and the entire job still has 60 minutes. A timeout remains a failed gate.

## Runner decision

Keep standard GitHub-hosted runners for the public source repository. The
installed workstation remains private and is not a CI runner.
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

The Qdrant source build now also uses the guarded SDK-space preparation and
requires at least 25 GiB free disk and 12 GiB RAM before building. The measured
r4 Docker command took 14 minutes 52.8 seconds with an 8.8203 GiB Rust compiler
cgroup peak, including file cache. Rust compiled from source; unchanged stages
used cache, so this is not a fully uncached or hosted measurement. See the
[Qdrant image qualification](../gateway/images/qdrant/README.md); concurrent
dashboard/tool stages and the runner OS also need headroom. The standard public Linux runner offers 4 CPUs and
16 GB RAM. The standard private runner's 8 GB does not meet this selected build
prerequisite: use a sufficiently provisioned disposable runner for a private
fork, rather than weakening the scan or attaching the live workstation.
See [GitHub runner specifications](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

The current heavy-image preparation deliberately requires a GitHub-hosted runner
before deleting preinstalled SDK directories. A future self-hosted design must
replace that preparation and qualify its isolation; changing `runs-on` alone is
insufficient. No self-hosted runner is installed by this decision.

References: [rerunning jobs](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs),
[runner isolation](https://docs.github.com/en/actions/reference/security/secure-use#hardening-for-self-hosted-runners),
[billing rules](https://docs.github.com/en/billing/concepts/product-billing/github-actions).
