# Coordinated dependency maintenance — 2026-09-27

The application/tooling changes proposed by Dependabot PRs #3–13 are coordinated
in one batch so the independently installed projects remain reproducible. This
document records the implementation decision and the verified dispositions below.

| Scope | Retained version | Original PRs |
| --- | --- | --- |
| Node / npm | 22.23.3 / 11.10.0 | Prerequisite for #5 |
| jsdom | 30.1.1 | #5 |
| MCP, agent / runbooks / API | 2.2.0 | #8, plus runbooks consistency |
| Pydantic / pydantic-core, agent / runbooks / API | 2.13.5 / 2.46.5 | #9, plus runbooks consistency |
| LangGraph, agent / API | 1.2.12 | #10 |
| Ruff, all four Python projects | 0.16.9 | Supersedes the 0.16.8 proposal in #7 and #13 |
| uv_build, agent / API / speech | 0.12.18 | #6, #11, #12 |
| actions/setup-node | 7.0.0 | #3 |
| astral-sh/setup-uv | 10.2.0 | #4 |

The uv executable remains 0.12.5. Existing transitive resolutions outside the
selected upgrades are retained. The control API lock updates the editable
agent's manifest metadata as well as checking its resolved versions; having an
adequate resolved version alone is insufficient for `uv sync --locked`.

## Provenance

The [official Node 22.23.3 release](https://github.com/nodejs/node/releases/tag/v22.23.3)
was published on 2026-09-23. The Linux x64 archive downloaded from nodejs.org was
checked against its [official SHA256 manifest](https://nodejs.org/dist/v22.23.3/SHASUMS256.txt):
`df450af89261115ef9f9e3830c3eeb2cc9213b63c720b1af623cb5dcbe2e02de`.
The local verification uses a private tool directory; it does not silently
replace the workstation's system Node. Install/select 22.23.3 explicitly for
both `apps/console` and `evals`; `.node-version` is the CI/runtime pin and the
package engine constraints enforce the minimum.

The following tag-to-commit mappings were verified through the upstream GitHub
API and are pinned in the workflows:

- [setup-node v7.0.0](https://github.com/actions/setup-node/releases/tag/v7.0.0):
  `820762786026740c76f36085b0efc47a31fe5020`.
- [setup-uv v10.2.0](https://github.com/astral-sh/setup-uv/releases/tag/v10.2.0):
  `c18668ad3cf93ea998bef934396af7bb5c839dc7`.

## PostgreSQL remains on the qualified 16.15 derivative

PR #2 changes PostgreSQL to 18.6 without adapting the data mount, migrating the
16 cluster, or validating LiteLLM. It is deliberately excluded. Dependabot still
tracks PostgreSQL minor/patch and digest changes, but major updates require an
explicit migration. PR #2 was closed with this decision documented in
[ADR 0016](adr/0016-maintenance-dependances-et-postgresql.md). It was not merged
or replaced by an equivalent PostgreSQL 18 change.

The 2026-09-26 image assessment remains unchanged: 0 critical / 166 high package
occurrences, with the qualification limits in
[the security release review](SECURITY-RELEASE-2026-09-26.md). This application
maintenance neither re-scans nor remediates that image baseline.

## Validation requirements

Use fresh environments from the committed locks, not previously installed
workstation packages. Run all four Python suites, branch coverage, Ruff, mypy
and package builds where applicable. The agent and control API suites include
real stdio MCP handshakes; the agent suite exercises checkpoint interruption,
human approval/refusal and invalid provenance. Keep the privacy-boundary tests.
Speech model qualification is separate: absence of local model assets causes
explicit integration skips rather than implying acoustic correctness.

With Node 22.23.3 and npm 11.10.0, run `npm ci --ignore-scripts --no-fund`, audit
and tests in both npm projects. For the console also run build, formatting,
E2E type checking and Playwright without retries. Browser fixtures use synthetic
data and port 8789; coordinate that port when multiple checkouts are active.

The initial read-only inventory and subsequent local evidence are outside Git
under `/home/vedric/platform/immersive-2026-09-27/`. Fresh-clone and hosted checks identify the integrated candidate commit below.
They preceded closure of the replaced Dependabot PRs.

## Observed local qualification

On 2026-09-27, fresh virtual environments and npm installations in an isolated
worktree based on `a81edde3` passed the following checks after these dependency
changes. This is local evidence, not a hosted CI claim or a result for later UI
changes being developed separately.

| Check | Result |
| --- | --- |
| Agent suite / branch coverage | 113 passed / 82% |
| Runbooks suite / branch coverage | 48 passed / 74% |
| Control API suite / branch coverage | 342 passed / 90% |
| Speech suite / branch coverage | 49 passed, 10 explicit model-integration skips / 72% |
| Console unit tests | 119 passed |
| Playwright desktop/mobile, retry count zero | 32 passed |
| Evaluation configuration tests | 2 passed |
| Image scanner unit tests | 10 passed |
| Python runtime audits / both npm audits | No known advisories found |

Ruff, the three mypy checks and package builds, console build/E2E typing/format,
standalone script locks, secret-hook tests and Compose syntax validation against
the example environment also passed. The skipped speech tests require local
model assets; this batch does not claim to have qualified the speech acoustics.
No Docker image build, PostgreSQL migration or live volume operation occurred.

## Final disposition — 2026-09-27

PRs **#3–13 are closed as superseded** by the coordinated batch in
[PR #16](https://github.com/Vedric/ambicrafted-platform-workspace/pull/16).
PR **#2 is closed as a declined, unqualified major database migration**; PostgreSQL
16 and its existing volume are preserved. The original proposals and review
history remain available. Closing a proposal is not evidence that its exact diff
was merged; the retained versions in the table describe the actual implementation.

Candidate `893bfb02dbb0dcd4788ef1005440bca1fe3645dc` passed all seven groups in a
fresh clone, with fresh environments and no operator secrets. Both hosted
[push CI](https://github.com/Vedric/ambicrafted-platform-workspace/actions/runs/36295392649)
and [PR CI](https://github.com/Vedric/ambicrafted-platform-workspace/actions/runs/36295394648)
passed all eight jobs, including actual offline speech models. The combined UI
suite contains 158 unit tests and 40 desktop/mobile browser journeys; speech has 51
quick tests plus 14 real integrations. The local service was synchronized from the
locks and restarted; nineteen readiness checks passed. The final merged commit
and zero-open-PR inventory are recorded in the operator delivery report.

## Follow-up proposals #17 and #18

The next Dependabot run opened two additional valid runbooks updates after the
initial batch. This follow-up, based on merged commit `0b82346d`, incorporates
[qdrant-client 1.19.1](https://github.com/qdrant/qdrant-client/releases/tag/v1.19.1)
from [PR #17](https://github.com/Vedric/ambicrafted-platform-workspace/pull/17)
and [pytest 9.1.1](https://github.com/pytest-dev/pytest/releases/tag/9.1.1)
from [PR #18](https://github.com/Vedric/ambicrafted-platform-workspace/pull/18).
Only those two versions change in the runbooks lock; pytest is a development
dependency. No server image, live volume or other project's lock changes.

That updater also attempted to replace the local editable agent with a public
PyPI homonym. [ADR 0018](adr/0018-provenance-des-dependances-locales.md) records
the targeted exclusions and retained source/CI guarantees. Confirmation that
the hosted updater no longer attempts these replacements requires its next
run after integration; it is not inferred from local tests.

Fresh local environments passed all 48 runbooks tests with 74% configured
branch coverage and all 113 agent tests, including real stdio transport and
provenance rejection. Runbooks Ruff checks, locked resolution and its runtime
dependency audit also passed; the audit found no known advisories. These are
local results for this isolated follow-up. A real MCP stdio handshake using
the new runbooks environment exposed the four expected read-only tools. A
synthetic PostgreSQL query returned the expected literal and semantic source
through the running local embedding gateway and Qdrant service; reading the
runbook verified its SHA-256 and full text. The transport closed normally, with
no indexing, collection mutation, model analysis or remediation request.

The integrated replacement still
requires fresh-clone and hosted CI qualification before closing PRs #17/#18 as
superseded. The dated container baseline remains unchanged.
