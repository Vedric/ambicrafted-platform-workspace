# Contributing

This repository has one organising idea, and everything below follows from
it: **a guardrail is only validated by an observed refusal.** A control that
has never been seen to say no is an intention, not a control.

## 🧭 The guiding principle

Writing the guard is the easy half. The half that counts is making it refuse,
on purpose, and keeping the proof.

Concretely, a change that adds or touches a guardrail is not finished until:

1. **A refusal has been observed.** Not reasoned about — run. Either a test
   that fails without the guard, or a recorded run with its output.
2. **The refusal is locked by a test that needs no network.** Every guardrail
   test in this repository runs on an unplugged machine. A guardrail that can
   only be checked in real conditions is not a guardrail.
3. **The proof is written down** where someone will find it: in the ADR for
   the decision, in the relevant README for the daily reader.

This is also why several sections of this documentation say *"not exercised by
a test"* rather than claiming coverage. Stating the gap is part of the
method; a plausible-but-false claim is worse than an admitted hole, because
people act on it.

The same standard applies to documentation. **Document only what you have
verified in the code or in execution.** If a behaviour is ambiguous, run it.
If you cannot verify it, write it as uncertain.

## ✍️ Conventions

### Conventional Commits (rule 6)

`type(scope): subject`, subject in the imperative, no trailing period.

Types in use: `feat`, `fix`, `chore`. Scopes in use, one per area of the
platform: `passerelle`, `agent`, `mcp`, `rag`, `evals`, `tracage`,
`securite`, `hooks`. Scopes are French, like every other identifier here.

```
feat(agent): agent SRE borné (budgets, liste blanche fermée, cloisonnement)
fix(hooks): passer -- à grep pour les motifs commençant par un tiret
chore: dettes soldées (images épinglées, RUNBOOK_DIR, purge checkpoints)
```

The body says *why*, and names what was verified. A commit that changes a
guardrail and does not say how the refusal was observed is incomplete.

### An ADR for every architecture decision (rule 5)

`docs/adr/NNNN-titre-en-francais.md`, next free number. Sections: Context,
Decision, Alternatives rejected, Consequences.

Two habits make these ADRs useful rather than ceremonial:

- **Consequences list costs, not only benefits.** Every ADR here names what
  its decision costs. One that does not has not been written honestly.
- **An ADR is dated and frozen.** It records a decision in the state of
  knowledge of its day, and is not rewritten when reality moves on. When a
  decision is superseded, write a new one that says so. (ADR 0004 completes
  0003; ADR 0005 completes 0004. Neither rewrote its predecessor.)

The index is at [`docs/adr/README.md`](docs/adr/README.md).

### Pinned dependencies (rule 7)

Container images by **digest**, recorded on the container actually running —
not on what the registry currently offers under a nearby name:

```sh
docker image inspect "$(docker inspect litellm --format '{{.Image}}')" --format '{{.RepoDigests}}'
```

The comment above each `image:` gives the version and the date of the reading.
Never go back to a moving tag (`latest`, `main-stable`, `16-alpine`): they
change content without changing name. ADR 0006 records a case where
`main-stable` happened to point at the right digest that day — a calendar
coincidence, not a guarantee.

Python dependencies get a floor for the API in use and a ceiling at the next
major: `httpx>=0.28,<0.29`, `mcp>=2,<3`, `langgraph>=1.2,<2`. Lock files are
committed.

## 🔧 Development setup

Python is managed by `uv` exclusively, never global `pip` (rule 3). Secrets
come from `.env` files loaded by `direnv` (rule 4).

```sh
git clone <repo> && cd workspace
direnv allow                        # loads .env at the root

# The agent, without the graph extra — this is the ADR 0003 footprint
cd agents/sre-agent && uv sync

# With the graph: two declarations, twenty-three packages (ADR 0004)
uv sync --extra graphe
```

The stack itself is described in [`gateway/README.md`](gateway/README.md) and
the day-to-day commands in [`docs/OPERATIONS.md`](docs/OPERATIONS.md).

### Running the tests

Everything runs offline. No gateway, no MCP server, no network.

```sh
cd agents/sre-agent
uv run --extra graphe pytest -q     # 49 tests
uv run --extra graphe pytest -q -k confidentielle    # just the compartment
uv run --extra graphe pytest -q tests/test_graphe.py

bash .claude/hooks/test-block-secrets.sh   # 15 checks, both directions
```

| File | Tests | Covers |
|---|---:|---|
| `tests/test_gardefous.py` | 23 | Compartmentalisation, both budgets, allow-list, token confinement, source guard, JSON extraction |
| `tests/test_graphe.py` | 20 | Human gate, resume, budget routing by edge, reducers, path journal, checkpoint purge |
| `tests/test_propagation_trace.py` | 6 | W3C `traceparent`, and that barrier 1 precedes both injection and network |

`tests/conftest.py` sets `SRE_TRACAGE=0` once rather than per test: an
exporter looking for an absent collector turns a test failure into a timeout
and hides the real result.

Two conventions worth copying when you add tests:

- **Substitute at the boundary, run the real code inside.** The graph tests
  replace `appeler_llm` and the tool client; budget, allow-list, confinement
  and source guard are the production code, executed as-is.
- **Trap the network with an assertion, not a mock that returns.** A refusal
  test should fail loudly if the network is reached:
  `monkeypatch.setattr(llm.httpx, "post", interdit)` where `interdit` raises.

### Before opening a change

```sh
uv run --extra graphe pytest -q                       # 49 passing
bash .claude/hooks/test-block-secrets.sh              # 15 passing
cd gateway && docker compose config --quiet && echo OK
git check-ignore -v gateway/.env .env                 # both must be ignored
```

Note what `docker compose config` does **not** prove: that images are
pullable, that services start, that they talk to each other, or that volumes
recreate correctly. `gateway/README.md` has the full list. Only the
"verify it works" section, run on a fresh machine, proves those.

## 📜 The eight rules, explained

They live in [`CLAUDE.md`](CLAUDE.md) as terse imperatives, because that file
is the operating contract read by coding agents. Here is what each one is
actually protecting.

### 1 — The code never names a provider model. Aliases only.

`smart`, `balanced`, `fast`, `local`, `local-embed`. The alias → model mapping
lives in `gateway/config.yaml` and nowhere else.

*Why:* changing model becomes one line of YAML instead of a search across the
codebase; and the frontier becomes a property of configuration rather than
something scattered through application code. A side effect worth knowing:
provider names still arrive in Tempo through the gateway's own telemetry, so
a dashboard that wants to reason in aliases must filter on
`resource.service.name` (ADR 0005).

*How it fails:* an unknown alias raises before any network call
(`test_alias_inconnu_refuse` uses a real model name as the negative case).

### 2 — No client data crosses the border.

Logs, configs, mission code. These payloads use the `local` alias through the
`confidential-only` virtual key.

*Why:* this is the reason the platform exists. Everything in
[`SECURITY.md`](SECURITY.md) is downstream of it.

*How it is enforced:* three independent barriers, not one. And the rule does
not distinguish data from metadata about data — which is why LangSmith was
rejected despite already being installed.

### 3 — Python is managed by `uv` exclusively. Never global `pip`.

*Why:* reproducibility. A committed lock file plus `uv sync` gives the same
environment on another machine; a global `pip install` gives whatever that
machine had.

### 4 — Every secret in `.env`, loaded by `direnv`. No hard-coded secret, not even in an example.

*Why:* "not even in an example" is the load-bearing half. Example values get
copied. Every value in `gateway/.env.example` is deliberately fake and says
so.

### 5 — Every architecture decision produces an ADR in `docs/adr/`.

*Why:* the expensive knowledge in this repository is not what was chosen, it
is what was rejected and why. ADR 0004 is 300 lines of measurement whose
conclusion is "the framework buys durability of state, not clarity of flow" —
that conclusion is worthless without the numbers behind it.

### 6 — Conventional Commits.

See above.

### 7 — Every container image and every dependency is pinned. Never a moving tag.

Pin **what is running**, verified on the live instance — not what the
registry offers under a nearby name.

*Why:* the distinction is the whole rule. `grafana/tempo:latest` in service
and `grafana/tempo:3.0.0` in the registry were two different builds; the
Compose file pins the digest of the one that was actually tested here.

### 8 — A secret is never displayed, not even to verify it.

No `cat`/`grep`/`echo` on a `.env`, no `docker inspect`, no `compose config`
without `--quiet`, no `env`/`printenv`. Verify by length and 12-character
prefix. **A command's output is a leak exactly as much as a file is.**

*Why:* this rule was bought with an incident. Four secrets were rotated on
2026-08-27 because they appeared in the *output* of commands — nothing was
ever written to a versioned file, `.env` stayed ignored, and the `deny Read`
rule was never bypassed. ADR 0007 is the post-mortem.

*What it does not give you:* the hook that backs it up sees only literals in a
command's text. It would have stopped none of the leaks that caused the
incident. It is a net against inattention, not a boundary — and a guardrail
wrongly trusted is worse than an absent one, which at least leaves vigilance
intact.

## 🌍 Language policy

**Documentation is in English. Identifiers stay in French. Operator-facing
text stays in French.** This is a deliberate split, and it is owned rather
than apologised for.

| What | Language | Examples |
|---|---|---|
| Documentation | **English** | `README.md`, `SECURITY.md`, `CONTRIBUTING.md`, everything in `docs/`, all sub-READMEs |
| Code comments and docstrings | **English** | module docstrings, inline comments |
| Identifiers | **French, unchanged** | `appeler_llm`, `OUTILS_AUTORISES`, `FuiteConfidentielle`, `actions_ecartees_sans_source`, `porte_humaine`, `SRE_MAX_APPELS_OUTILS`, `0003-agent-sre-borne.md` |
| System prompts | **French** | `SYSTEME_EXTRACTION`, `SYSTEME_RAISONNEMENT`, `CONSIGNE_NON_FIABLE` |
| Operator-facing messages | **French** | CLI output, error messages, `budget épuisé, escalade humaine requise` |
| `CLAUDE.md` | **French** | it is an agent operating contract, adjacent to a system prompt |

### Why documentation in English

The documentation is the part meant to travel: to a reviewer, to a future
maintainer, to anyone assessing whether the security argument holds. English
is the working language of the ecosystem this platform sits in — OpenTelemetry
semantics, LiteLLM, MCP, LangGraph — and the ADRs constantly quote it.

### Why identifiers stay French

Not inertia — a risk calculation.

This is security code. Forty-nine tests cover it and **every guardrail was
validated by an observed refusal**. A mass rename would touch
`llm.appeler_llm`, `OUTILS_AUTORISES`, `Classification`, the graph node
names — which are also persisted state values in checkpoint files — and the
`ambicrafted.*` trace attributes that existing Grafana queries depend on.

That is real risk for a cosmetic gain. The rename would have to be re-proved
in full: every refusal re-observed, every checkpoint format re-checked, every
saved query re-pointed. Nothing about the platform's behaviour would improve.

So the split is drawn where the cost/benefit actually falls: **prose in
English, because prose is read; symbols in French, because symbols are load-
bearing and renaming them buys nothing.**

### Why operator-facing text stays French

The operator is French-speaking, the runbooks are in French, and the local
model answers in French. An agent that reports `budget épuisé, escalade
humaine requise` in the same language as the runbook the on-call engineer is
about to open is doing its job. Translating those strings would put a
language boundary in the middle of an incident, at 3 a.m., which is exactly
where you least want one.

### In practice

- Adding a function? English docstring, French name.
- Adding an error message the operator will read? French.
- Adding an exception class? French name, English docstring.
- Adding an ADR? English content, French file name, next free number.
- Quoting an identifier in English prose? Leave it in French, in code font,
  and gloss it if the meaning is not obvious — as this documentation does
  with `porte_humaine` (human gate) and `actions_ecartees_sans_source`
  (actions discarded for lack of a source).
