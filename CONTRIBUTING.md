# Contributing

A guardrail is validated by an observed refusal. A change to a trust boundary
needs a test that exercises the real guard, substitutes only the outside
boundary, and demonstrates that forbidden work did not happen.

## Conventions

Use Conventional Commits: `fix(agent): ...`, `fix(mcp): ...`, `ci: ...`,
`docs: ...`. Architecture changes need a dated ADR with Context, Decision,
Alternatives rejected and Consequences. Historical ADRs are not rewritten;
a newer ADR explicitly supersedes the affected behavior.

Documentation and developer comments/docstrings are English. Identifiers
remain French. Operator messages, prompts, runbooks and MCP tool descriptions
are French. Config metadata/comments and test assertion messages keep their
existing French convention. `CLAUDE.md` is the French operating contract.

Python uses uv exclusively. Direct requirements have bounded compatible
ranges or exact tool versions; committed locks resolve exact versions. Use
`--locked` to reject a stale lock, not `--frozen` to skip that check. Images
must be pinned by digests of versions actually started and verified in the
validation stack. Model artifacts have their own digest manifest.

## Setup and checks

```sh
uv sync --locked --project agents/sre-agent --extra graphe
uv sync --locked --project mcp-servers/runbooks
uv run --locked --project agents/sre-agent pytest agents/sre-agent/tests -q
uv run --locked --project mcp-servers/runbooks pytest mcp-servers/runbooks/tests -q
bash .claude/hooks/test-block-secrets.sh
```

Run lint from each project directory, since import resolution depends on the
project root. Run `uv run --no-sync mypy` and `uv build` from the agent project.
The dev locks pin Ruff, coverage and mypy. Scripts under `scripts/` have
standalone uv script locks. Check them with the pinned Ruff used by the agent.

For network isolation, install first, then execute in a fresh namespace:

```sh
cd agents/sre-agent
unshare -rn uv run --no-sync pytest -q
```

Also run a negative network control and confirm it fails. Proxy variables
alone do not prove all clients are offline. Unit fixtures reject accidental
socket connections and replace HTTP/MCP boundaries explicitly.

A source-provenance test must include an actual successful read envelope.
Do not restore the old behavior by assuming that a filename alone is evidence.
Include negative cases: invented/unread source, incomplete envelope, changed
hash, dropped negation or prerequisite, human refusal and reused thread.

## Fresh-clone evidence

Do not claim CI from a working tree with existing virtual environments and
secrets. Validate the intended commit in a fresh clone, synchronize from locks,
run the workflow commands, build the package, and validate Compose against
`gateway/.env.example` using `config --quiet`. Never print resolved configuration.
A local reproduction is not proof of the hosted Actions run or branch protection.

The workflow checks all four Python projects, typing, packaging, dependency
advisories, the secret hook, Compose syntax, evaluation configuration and the
React console build, unit tests, desktop/mobile browser flows and accessibility.
Real model evaluations and service smoke tests run separately with synthetic
inputs; CI does not need provider secrets.

## Secret scanning before commit

The existing pre-commit hook runs ggshield 1.54.0. As recorded in ADR 0008,
it sends the **staged diff** to GitGuardian's detection API. Do not stage any
customer data here. The scan token belongs only in the private root `.env`.

```sh
uv tool install pre-commit==4.5.1
pre-commit install --install-hooks
direnv exec . git commit
```

A missing token or scanner error blocks the commit. Do not bypass with
`--no-verify`, `SKIP=ggshield`, a disabled hook, or an alternative hook directory.
Fix the configuration or the flagged value. Rewrite test fixtures so they do
not look like real keys; any unavoidable ignored match needs a named, reviewed
entry. Never print the secret to diagnose the scanner.

The Claude tool-input hook is a separate control: deny recognizable literal
secrets, deny malformed hook input, and remain neutral on normal commands.
Neither that hook nor a commit scanner makes command output safe. Never run
commands that print credentials or private environment contents.

## Review and scope

Document changed behavior, evidence and limitations, rather than only listing
files. Keep production data and validation resources separate. Clean only
resources created by the test; this workstation hosts unrelated projects.
Update security statements when code behavior changes. A test pass is not
permission to claim model correctness or disregard a dependency advisory.
