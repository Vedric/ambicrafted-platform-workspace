# ADR 0018 — Preserve local dependency provenance in automated updates

Date: 2026-09-27

Status: Accepted; hosted updater verification required after integration

## Context

The control API installs `sre-agent[graphe]==0.1.0` from the editable repository
path `../../agents/sre-agent`, declared in `tool.uv.sources`. It does not consume
the public PyPI project sharing that name. Dependabot's
[uv update job](https://github.com/Vedric/ambicrafted-platform-workspace/actions/runs/36296048340)
queried that public project and attempted to resolve version 0.2.1 for both
`sre-agent` and `sre-agent[graphe]`. The local package remains 0.1.0, so resolution
failed. This failure is independent of the valid runbooks updates proposed in
PRs #17 and #18.

## Decision

Ignore exactly `sre-agent` and `sre-agent[graphe]` in the uv Dependabot update
configuration. Keep all four uv project directories, every other dependency
update, security checks and existing lock validation enabled. Maintain the local
package through repository changes and regenerate its consumers' locks when its
manifest changes. Do not replace the editable source with a registry package or
raise its version to satisfy the unrelated public release.

The [documented name matching](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference#ignore)
supports `*` wildcards. Source review at Dependabot commit
`f3a79fa0711aca171b2174b855d9f21b16237961` confirms that
[the matcher](https://github.com/dependabot/dependabot-core/blob/f3a79fa0711aca171b2174b855d9f21b16237961/common/lib/dependabot/config/update_config.rb)
escapes other characters rather than treating brackets as a glob character
class. Its
[Python name normalizer](https://github.com/dependabot/dependabot-core/blob/f3a79fa0711aca171b2174b855d9f21b16237961/python/lib/dependabot/python/name_normaliser.rb)
removes extras; the uv ecosystem reuses that normalizer. Both observed spellings
are retained explicitly, with no broad prefix wildcard. This source review is
not a completed hosted updater run.

Apply qdrant-client 1.19.1 and pytest 9.1.1 only in the standalone runbooks
project. Keep the server image, all other resolved runtime packages and the
corpus unchanged. Qualify the pinned client with the runbooks tests and a real
read-only MCP query against the existing local gateway and Qdrant service.

## Alternatives rejected

- Disable uv updates entirely: this would suppress maintenance of unrelated
  third-party packages.
- Ignore every `sre-*` package or remove the locked-installation gate: both
  conceal a broader class of changes than the observed naming collision.
- Adopt the public version or publish this private local package to fix an
  updater error: neither follows the repository's source provenance contract.
- Close the valid runbooks PRs without equivalent qualified changes: this would
  remove visible proposals while retaining their dependency backlog.

## Consequences

The repository owner must review future local-agent version and manifest changes;
Dependabot will not propose public registry updates for that name. The existing
CI continues to install committed locks, test the agent/API contract and audit
third-party runtime dependencies. This ignore is a provenance correction, not a
vulnerability exception or evidence of a clean container-image baseline.

After integration, inspect a new hosted uv updater job to confirm the two
resolution errors are absent and unrelated updates still run. Local YAML,
matching and lock checks cannot establish that hosted behavior. Updated PRs are
closed as superseded only after the integrated replacement passes its checks.
