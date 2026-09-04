# Security

This platform processes operational data from banking, energy and defence
clients on a single workstation. Its security argument is narrow and
deliberate: **a small number of things cannot happen, because a code path
refuses them — and every one of those refusals has been observed.**

Nothing here claims that the models behave well. The claim is about what the
surrounding code allows them to reach.

## 🎯 Threat model

### Assets

| Asset | Where it lives | Worst case |
|---|---|---|
| Raw client alerts | in memory during a run; never written by the agent | leaks to an external provider |
| Alert-derived extracts | graph checkpoints (`~/.local/state/sre-agent/graphe.sqlite`, `0600`) | readable by another local user; retained indefinitely |
| Provider API key | `gateway/.env` (`0600`), gateway container environment | spend on someone else's behalf; provider-side abuse |
| Virtual keys | `.env` at the workspace root; hashed in the gateway's Postgres | bypass of the `confidential-only` compartment |
| Gateway master key | `gateway/.env` | full control of the gateway: key creation, unlimited spend |
| Runbook corpus | `runbooks/*.md`, versioned | tampering, to make the agent recommend a harmful action |
| Spend history | gateway Postgres | not confidential; loss is acceptable, it is not rebuildable |

### Threats and mitigations

| # | Threat | Mitigation | Verified by |
|---|---|---|---|
| T1 | Client data reaches an external provider | Three independent barriers, from `llm.appeler_llm` to the gateway configuration | `FuiteConfidentielle` with zero network calls; gateway 403 on a cross-alias attempt |
| T2 | Prompt injection carried by an alert makes the agent act | Untrusted data is confined between per-run tokenised markers; instructions are reported, never followed | An injection-bearing alert was reported and not followed; the hostile text never enters the frontier payload |
| T3 | Injection carried by a **runbook** (tampered corpus) | Runbook contents are wrapped by the same `prompts.bloc()`; the system prompt states they inform, they do not command | Same confinement mechanism; the corpus is versioned and reviewed |
| T4 | The agent modifies production | It has no tool that writes. Not a prompt rule — no function in the package exposes a shell, a file write or arbitrary HTTP | Closed allow-list of four read-only tools; out-of-list names refused before the session is consulted |
| T5 | Uncontrolled cost drift | Two budgets held by the calling code, which the model can neither read nor modify | Both caps reached in execution, clean stop, exit code 2 |
| T6 | An invented procedure gets executed by a tired human | `runbook_source` is nullable and the code acts on it: unsourced actions are removed and replaced with an escalation | Out-of-corpus TLS alert: no procedure invented |
| T7 | A diagnostic is delivered without anyone seeing it | Durable human gate before delivery (graph implementation) | Survived `SIGKILL`; silence is not approval |
| T8 | Path traversal through a tool argument | `_resoudre()` refuses separators and leading dots, then re-checks containment after resolution | Refusal returned as a message to the model, not an exception |
| T9 | Code execution through the checkpoint file | Deserialisation allow-list, `pickle_fallback=False`, four named types | **Not exercised by a test** — see the honesty note below |
| T10 | A secret enters an agent transcript | Rule 8: a secret is never displayed, even to check it. Verification by length and 12-character prefix | Hook tested in both directions; and the incident of ADR 0007, which is what produced the rule |
| T11 | A supply-chain change lands silently | Every image pinned by digest recorded on the running container; every dependency bounded floor-and-ceiling | `docker-compose.yml`, `pyproject.toml` |
| T12 | Network exposure of the stack | Every published port bound to `127.0.0.1`; Postgres not published at all | `docker ps` port mapping |
| T13 | A real secret reaches the pushed history | Placeholders written as instructions, never as random-looking strings; `ggshield` refuses the commit on the staged diff before it exists; GitGuardian's GitHub integration detects on the pushed history (external, after the fact, blocks nothing) | **Refusal observed in this repository on 2026-09-04**: two fake keys of valid form staged, `2 secrets detected`, exit code 1, `HEAD` unchanged; and the passing direction, a commit of placeholder forms accepted. Plus two dashboard incidents on 2026-08-27, raised within minutes of the push, both established as false positives by prefix, never by value (`4949a30c`) |

### What is explicitly **not** covered

This section matters as much as the one above. A threat model that lists only
what it defends against is marketing.

- **Leaks through tool output into an agent transcript.** This is the central
  known gap and it is structural, not an oversight. A `PreToolUse` hook sees
  a command, never its output; a `PostToolUse` hook sees the output only
  after it has entered the context, and cannot rewrite it. Neither of this
  repository's two secret-scanning hooks would have stopped **any** of the
  leaks that caused ADR 0007, and adding the second one did not narrow this
  gap by a single case — see
  [The two hooks](#the-two-hooks-different-moments-one-shared-blind-spot).
  What protects is a human and an agent applying rule 8 before running a
  command, not a hook.
- **A malicious local user.** The machine is single-user by assumption.
  Process arguments are briefly visible in `/proc`; the `0600` checkpoint
  file and the `0700` directory raise the bar but do not defend against root.
- **The provider itself.** Data sent across the border is trusted to the
  provider's own controls. The compartment exists precisely so that client
  data is never in that category.
- **Model output quality.** No guardrail here makes a diagnostic correct.
  They make an *unsourced* diagnostic visibly unsourced, and an
  *over-budget* run stop rather than degrade. A sourced diagnostic can still
  be wrong.
- **Anonymisation completeness.** The extraction step is performed by a local
  model, which is better than regular expressions at proper nouns and
  business identifiers, but it is a model: it can miss one. The compartment
  is what makes this tolerable — the extract goes to the frontier, but the
  raw alert never does, so a missed identifier is a degradation, not a
  breach of the primary rule.
- **Availability.** Nothing here is redundant. This is a workstation.
- **`langsmith`, present and unused.** It is a hard transitive dependency of
  `langgraph` that by default seeks to export telemetry off the machine.
  `LANGSMITH_TRACING=false` is set explicitly and it is inert without an API
  key, but it must be re-examined at every version bump.
- **Two trace paths remain unattached** (the MCP server's embedding call, and
  the `mcp` SDK's own spans). This is an observability gap, not a data-flow
  gap: those calls still go through the gateway on `local-embed`.

## 🛡️ The seven controls

Each one is a place where code refuses, and each entry names how that refusal
was observed. Two further controls exist that are **not** refusals, and a
third-party secret scanner whose local half does refuse but is not this
repository's code and does not work without a network call. All three are
listed separately below rather than padded into this table.

### 1 — Tool-call budget

`budget.py`. A cap on tool calls per alert, default 10, `SRE_MAX_APPELS_OUTILS`.

A budget is not an instruction given to the model: it is a counter held by the
calling code, which the model can neither read nor modify. It is decremented
**before** execution, so a refused call never reaches the MCP server.

> **Observed refusal.** `SRE_MAX_APPELS_OUTILS=2` → clean stop when refusing
> the third tool, exit code 2, no diagnostic (ADR 0003). In the graph, the cap
> is opposed by the routing edge, so a burst of three tools requested with two
> remaining is refused **as a whole** and no tool from that burst reaches the
> server. Locked by `test_le_budget_est_decompte_avant_execution` and
> `test_budget_outils_route_vers_abandon`.

Design point worth its own line: **the tools stay declared to the model even
when the budget is spent.** Removing them would make the model answer without
having consulted the runbooks, and that degraded answer would be returned as
a diagnostic. A budget must be opposed at the moment of the attempt, not
worked around upstream.

### 2 — Monetary budget

`budget.py`. A cap in USD per alert, default 0.50, `SRE_MAX_COUT_USD`.

Charged from the cost the gateway reports in its response headers. The agent
holds no price table — which would force it to know model names, in breach of
rule 1. The overrun is therefore *observed*, never predicted, and it
interrupts the following step.

> **Observed refusal.** `SRE_MAX_COUT_USD=0.05` → clean stop, exit code 2
> (ADR 0003). Locked by `test_budget_monetaire_leve_au_depassement` and
> `test_aucun_appel_engage_une_fois_le_plafond_atteint`.

Both budgets fail identically: stop, `budget épuisé, escalade humaine
requise`, no diagnostic. A partial diagnostic presented as complete would be
more dangerous than no diagnostic.

### 3 — Read-only, by absence of the tool

`outils.py`. There is no shell, no file write, no arbitrary HTTP anywhere in
the package. Not because a prompt forbids it — because no function exposes
them. Security comes from the absence of the tool.

Second layer: `OUTILS_AUTORISES` is a **closed** allow-list of four read-only
tools. A tool the MCP server might publish without appearing there is never
presented to the model. Adding a tool is a decision of this repository, not a
consequence of a server update.

> **Observed refusal.** `client.appeler("ecrire_runbook", …)` returns
> `"Refusé : 'ecrire_runbook' n'est pas un outil de cet agent"`, and the
> refusal happens **before** the MCP session is consulted — verified by
> calling it on a client that was never started, where any later access would
> have raised instead. Locked by
> `test_outil_hors_liste_blanche_refuse_sans_session` and
> `test_la_liste_blanche_tient_dans_le_noeud_d_outils`.

Third layer, inside the server: `_resoudre()` refuses any name containing a
separator or starting with a dot, then re-checks containment in `RUNBOOK_DIR`
after resolution. The file name returned by a Qdrant payload is re-validated
before being offered to the model, because that payload comes from outside
the process.

### 4 — Data compartmentalisation

`llm.py`, `config.py`, `gateway/config.yaml`. Every LLM call goes through
`appeler_llm`, which takes a mandatory `Classification`. There is a single
place to read to know whether client data can leave, and a single place to
change to make that no longer true.

Three barriers, independent — none assumes the others are correct:

1. **Application guard.** `CONFIDENTIEL` + a frontier alias raises
   `FuiteConfidentielle` before any network access. It is decidable rather
   than interpretable because `ALIAS_LOCAUX` and `ALIAS_FRONTIERE` are a
   strict partition, asserted by a test.
2. **Restricted virtual key.** A confidential payload travels with
   `CONFIDENTIAL_KEY`, restricted gateway-side to `local` and `local-embed`.
   The gateway answers 403 if the first barrier fell.
3. **No fallback out of `local`.** A local error has no path to the frontier.
   `router_settings.fallbacks` deliberately omits it.

> **Observed refusal.** A confidential payload aimed at each of the three
> frontier aliases raises `FuiteConfidentielle` with **zero network calls
> attempted** and zero cost — verified with `httpx.post` replaced by an
> assertion that fails if reached. Independently, the gateway answered
> `key not allowed to access model` on a `confidential-only` → `smart`
> attempt on 2026-08-24 (ADR 0001). Locked by
> `test_charge_confidentielle_refusee_sur_frontiere`,
> `test_charge_confidentielle_refusee_dans_le_graphe` and
> `test_le_refus_precede_l_injection_et_le_reseau`.

The MCP server's semantic search embeds its query through the same
`local-embed` alias with the same restricted key: the search query does not
leave the machine either.

### 5 — Untrusted-data confinement

`prompts.py`. Two kinds of text enter the context: instructions, written in
this repository and reviewed; and untrusted data — the alert text, from a
monitoring system we do not control, and runbook contents, from editable
files.

They are **never concatenated**. Untrusted data is always wrapped by
`bloc()`, between two markers carrying a random token drawn once per run. The
token is not cryptography: it removes from whoever writes the alert the
ability to write the closing marker, since they cannot guess it.

The associated instruction is constant: what is inside a block is described,
not executed, and any instruction encountered is **reported** in a dedicated
field. Reporting an injection is itself diagnostic information — an alert
carrying an injection is probably forged.

> **Observed refusal.** A forged closing marker does not close the block: the
> real marker appears exactly once, at the end, written by us. An
> injection-bearing alert had its instruction reported and not followed
> (ADR 0003). The recorded hostile text **stays local**: the triage payload,
> which crosses the border, excludes `instructions_detectees` entirely — only
> the count goes on. Locked by `test_une_alerte_ne_peut_pas_fermer_le_bloc`,
> `test_l_alerte_n_est_jamais_concatenee_a_une_instruction` and
> `test_le_texte_d_injection_ne_franchit_pas_la_frontiere`.

### 6 — Source guard

`modeles.py`. `Diagnostic.runbook_source` is nullable on purpose. A model
required to give a source invents one; a model allowed to declare it has none
provides the most useful line of the report.

`appliquer_garde_source()` then acts on that declaration rather than on the
prose: it removes the actions from `actions_proposees`, moves them into
`actions_ecartees_sans_source`, replaces them with a human escalation, and
adds "runbook missing from the corpus" to the missing elements. They are not
deleted — they stay visible, they simply stop being presented as procedures.

> **Observed refusal.** An out-of-corpus TLS alert produced
> `runbook_source = null`; the code discarded the actions and no procedure was
> invented (ADR 0003). Locked by
> `test_action_sans_source_est_ecartee_par_le_code` and its positive
> counterpart `test_action_sourcee_est_conservee`.

### 7 — Durable human gate

`graphe.py`, graph implementation only. `porte_humaine` calls `interrupt()`:
LangGraph writes the complete state to SQLite and hands control back
**before** the diagnostic is delivered.

Of all the controls, this is the only one that bounds not what the agent
*does* but what it earns the right to *hand over*. And it is durable, which
is the point: the property holds even if the machine stops during the pause.

> **Observed refusal.** Silence is not approval — `_lire_decision` treats
> anything that is not an explicit agreement as a refusal, yielding
> `rejete_par_humain` with nothing delivered. The process was `SIGKILL`ed
> during the pause; a fresh process resumed on the same `thread_id` and
> delivered in **1.28 s for 0.00 USD**, budget and tool history intact
> (ADR 0004). Locked by `test_le_graphe_s_arrete_avant_de_livrer`,
> `test_le_silence_ne_vaut_pas_approbation`, `test_un_refus_ne_livre_rien`
> and `test_la_reprise_repart_du_meme_point`.

### The two that are not refusals

Stated separately, because calling them "controls with observed refusals"
would be false.

**Traceability** (`tracage.py`) is an *observation* control. One parent span
`task.incident_analysis` per run, each LLM call and each tool call as a child
span, carrying data classification, cost, alias and outcome. Since ADR 0005
the gateway's spans attach beneath the agent's, so one alert is one trace —
measured again while writing this documentation: 52 spans, 10 from
`sre-agent` and 42 from `litellm-gateway`, single root, 5/5 LLM calls
attached. Tracing never fails the agent: if Tempo is unreachable the export
fails in a background thread and the analysis continues. That property is
also a trap — see
[`OPERATIONS.md`](docs/OPERATIONS.md#traces-are-not-arriving-in-tempo).

**Deserialisation allow-list** (`graphe.py`) closes a surface the framework
opened. `TYPES_PERSISTABLES` with `pickle_fallback=False` restricts what the
SQLite checkpoint may reconstruct to four named types. It is a real control
and it is held by this repository rather than by the framework — but **no
test currently exercises its refusal**, so it is listed here rather than
among the seven.

### Secret scanning: ggshield and GitGuardian

Its own category, for a reason different from the two above. There are two
halves here and they are not the same kind of thing: `ggshield` **refuses** a
commit on this machine; the GitGuardian dashboard **detects** on what has
already been pushed. Neither is this repository's own code, and both depend
on a third party being reachable, which is why they sit here rather than
among the seven.

#### The local half: ggshield refuses the commit

`.pre-commit-config.yaml` runs `ggshield` on the **staged diff** at every
commit (revision pinned to the one in service, rule 7). It sends that diff to
GitGuardian's detection API; what that send does and does not expose is
[ADR 0008](docs/adr/0008-diff-indexe-vers-l-api-gitguardian.md).

Observed on 2026-09-04, in this repository — not in a sandbox — on a staged
file carrying two fake keys of valid form, an AWS access-key/secret pair and
a high-entropy string:

```
ggshield (pre-commit)....................................................Failed
- hook id: ggshield
- exit code: 1

> commit://staged/tmp-test-ggshield.env: 2 secrets detected

>> Secret detected: Generic High Entropy Secret
   Validity: No Checker
>> Secret detected: AWS Keys
   Validity: Invalid
```

`HEAD` did not move. Three things in that output are worth keeping:

- **The values are masked** in the report, never printed in full. The refusal
  does not itself become the leak (rule 8).
- **`Validity: Invalid`** means GitGuardian *tested* the AWS pair against
  AWS. Detection is not only pattern matching: a credential that is staged is
  a credential that gets tried. For a real one, that is one more reason the
  answer is rotation and not deletion.
- **ggshield's own remediation text advertises `SKIP=ggshield git commit`.**
  It is not an option here, for the same reason `--no-verify` is not — see
  [`CONTRIBUTING.md`](CONTRIBUTING.md#the-pre-commit-hook-ggshield).

The other direction was exercised too, which is the standard applied to every
control in this document: a commit carrying the repository's ordinary
placeholder forms (`<openssl rand -hex 16>`) passes — `Passed`, commit
created.

Two traps came out of that test, both of which refuse a *clean* commit:

- **`ggshield` writes `.cache_ggshield` at the repository root** and, if that
  path is not already ignored, **appends its own entry to `.gitignore`**.
  `pre-commit` then fails the commit with `files were modified by this hook`,
  with `No secrets have been found` printed immediately above it. The entry
  is committed here so that ggshield never needs to write it.
- **`pre-commit` stashes unstaged changes before running the hooks.** A fix
  that exists only in the working tree is invisible to them. This is why that
  `.gitignore` entry has to be *staged* to take effect on the very commit
  that introduces it.

#### The external half: the GitGuardian dashboard

GitGuardian watches the GitHub repository through its GitHub integration and
opens an incident on its dashboard when a commit matches one of its
detectors. It is a real control and an independent one: it owes nothing to
the hooks, the tests or the discipline described in this document, which is
exactly why it is worth having. It proved itself live on 2026-08-27 — two
"Generic Password" incidents on `gateway/.env.example`, the first raised at
19:34 UTC, within minutes of the push (commits `121287a` and `ed18b2d`; false
positives, established and handled on 2026-09-02 in `4949a30c`).

What it does, and what it does not:

- **It detects after the push.** When the incident appears, the value is
  already on GitHub: in the history, in every clone, in any mirror or cache.
  A real secret caught this way is not caught, it is exposed, and the only
  answer is rotation. That window, between the commit and the alert, is
  exactly what the local half closes.
- **It blocks nothing.** No push is refused, no commit is rewritten. This is
  detection, not prevention.
- **It does not read `.gitguardian.yaml`.** That file is read by `ggshield`
  only, locally and in CI. The dashboard's path exclusions live in the
  workspace settings, and `ggshield` does not report its own ignores to the
  dashboard: the two are configured separately and can disagree.

**When an incident lands**, in this order — the first step is not optional:

1. **Establish whether a real secret is involved, by prefix, never by
   value.** For each secret in service, read its first 10 characters from
   the ignored `.env` into a shell variable and count the lines of
   `git log --all -p` containing them; print the count and the length, never
   the variable. A format token (`sk-ant-api03-`, `sk-master-`) legitimately
   matches the hook's regex and the test fixtures, so count again at 11, 12
   and 14 characters: the count must reach zero at the first character of
   secret material. This is the method applied in `4949a30c`; a scratch
   script that prints only lengths and counts is the right tool.
2. **False positive:** close the incident on the dashboard as *false
   positive*, with a comment naming what the value was (a placeholder, a test
   fixture) and where the check of step 1 is recorded. Then make the value
   undetectable so the alert cannot return: a placeholder reads as an
   instruction, `<openssl rand -hex 16>`, never as a random-looking string.
3. **Real secret:** rotation first, before any report or clean-up, following
   [`gateway/README.md`](gateway/README.md) — rotate, do not clean (below).
   The incident closes only once the new value is verified end to end and the
   old one revoked.

The risk that matters is not the false positive. **An alert that keeps firing
on a known false positive trains its reader to close alerts without reading
them, and that is the day the real one goes past.** Narrow exclusions and
undetectable placeholders are what keep this control worth reading.

### The two hooks: different moments, one shared blind spot

Two hooks now scan for secrets, and both the reason to keep both and the
reason neither is sufficient have to be written down, or someone will read
the pair as complete coverage.

| | `.claude/hooks/block-secrets.sh` | `ggshield` (`.pre-commit-config.yaml`) |
|---|---|---|
| Fires on | a Claude Code tool call, before it runs | `git commit`, before the commit exists |
| Reads | the literal text of `content`, `new_string` or `command` | the staged diff |
| Covers | this agent, this session | every commit, whatever the editor or the author |
| Detects | seven prefix patterns, hard-coded | GitGuardian's detector set, plus validity checks |
| Needs the network | no | yes; on failure the commit is refused, never skipped |

Neither subsumes the other, and the overlap is smaller than it looks. A value
pasted into a `Bash` command that is never committed is seen only by the
first. A secret written by hand in an IDE, by a script, by `make`, or by a
different agent is seen only by the second. Removing either one removes cases
the other never covered.

**What neither of them sees is the output of a command.** This is the gap of
[ADR 0007](docs/adr/0007-secret-fuite-par-la-sortie.md), and adding
`ggshield` did **not** close it — it was never a candidate to. The incident
that produced rule 8 leaked four secrets through neither hook's channel:
`cat`, `docker inspect`, `docker compose config` and `printenv` printed them
into an agent's context. Their command text contains no secret and they write
no file, so the first hook approves them; nothing is staged, so the second
never runs. **Both hooks approve all four today, unchanged.**

The same holds for every indirection ADR 0007 lists — a value in a shell
variable, a substitution, a glob, a heredoc assembled at runtime, a value
pasted into the conversation by the human. `ggshield` catches such a value
only if it later reaches a staged diff, which is the file channel again, not
the output channel.

So the honest statement of coverage is: **the file channel is now covered
twice; the output channel is still covered zero times.** What protects there
is rule 8, applied by a human and by an agent *before* running a command, and
nothing in this repository enforces it. This paragraph exists so that reading
the two hooks as "secrets are handled" takes effort.

## 🔑 Secret handling

### The rule

**A secret is never displayed, not even to verify it** (rule 8 of
[`CLAUDE.md`](CLAUDE.md)). Verification is by length and 12-character prefix:

```sh
v=$(sed -nE 's/^LITELLM_MASTER_KEY=//p' .env); echo "len=${#v} prefix=${v:0:12}"
```

The prefix distinguishes an old value from a new one, cannot reconstruct it,
and can be compared by eye. What it does **not** prove is that the key is
valid — only an end-to-end call returning 200 proves that.

A value transits only through shell variables: generated by `openssl rand`
into a variable, written by `sed` from that variable, passed to `psql` on
**stdin**, to `curl` through `-H "Authorization: Bearer $V"`. Never as a
literal argument, never through an output.

### What never leaves

| Never in the repository | Never on screen |
|---|---|
| `gateway/.env`, workspace `.env` (ignored, `0600`) | file contents (`cat`, `head`, `grep`, `sed -n p`) |
| Docker volumes (`gateway_*`) | `docker compose config` without `--quiet` — it interpolates every `${VAR}` |
| Checkpoint file | `docker inspect` — the complete `Config.Env` |
| Any real key, including in examples | `env`, `printenv`, `set`, `export -p`, `direnv export` |
| | `echo "$VAR"`, `set -x`, `curl -v`, debug logs |

`gateway/.env.example` is versioned and every value in it is a placeholder
written as an instruction in angle brackets (`<openssl rand -hex 16>`), never
a random-looking string: a generic password detector cannot mistake it for a
secret (two GitGuardian "Generic Password" false positives on the former
`FACTICE-…` form taught that lesson). Its `ANTHROPIC_API_KEY` placeholder is
kept short on purpose so that it does not match the hook's own pattern — a
test asserts the real file stays editable. `.gitguardian.yaml` at the root
excludes this one file from `ggshield` scans (pre-commit, CI); what that file
does and does not cover is in
[Secret scanning](#secret-scanning-ggshield-and-gitguardian).

### Rotation

Full procedure in [`gateway/README.md`](gateway/README.md). Three points that
cost time when learned the hard way:

- **`docker compose restart` does not re-read `env_file`.** Only `up -d`
  recreates the container with the new environment.
- **Postgres and Grafana read their password only at first initialisation of
  their volume.** Changing `.env` is not enough; the value must be applied
  inside the service.
- **Testing the PostgreSQL password on loopback inside the container proves
  nothing**: the official image's `pg_hba.conf` sets `127.0.0.1` to `trust`.
  Test from the Compose network, where `scram-sha-256` applies.

Method, from the ADR 0007 post-mortem: **one rotation at a time**, verified
**end to end** before the next; revoke the old value **after** that success,
never at the same time as creating the new one; on failure, one retry, same
protocol. Three keys created and revoked inside an hour left a dead key in
`.env`, and the diagnosis cost more than the rotation.

### After any exposure: rotate, do not clean

A value that has passed through a model context is compromised, whatever
follows. It is in the local transcript, in context summaries, and in anything
that reuses them. Transcripts cannot be reliably purged. This is not a
theoretical position — it is what ADR 0007 records, and it cost a full
rotation of four secrets.

## 📮 Reporting a vulnerability

This is a single-operator platform with no public deployment, so there is no
security mailbox and no coordinated-disclosure timeline to promise.

- **If you have access to the repository**: open an issue, or a direct
  message to the maintainer for anything you would not want in an issue
  title.
- **Never paste a real secret** into an issue, a pull request or an agent
  session. If a key is involved, say *which* key, by name and 12-character
  prefix, and rotate it first.
- **If a secret has been exposed**, rotation comes before the report. Follow
  the procedure in [`gateway/README.md`](gateway/README.md), then write up
  what happened.
- **A guardrail that can be bypassed is a finding**, even without impact. The
  premise of this repository is that these seven controls hold; a
  demonstration that one does not is the most useful thing you can send, and
  the fix will come with a test that reproduces the bypass.

Include: what you did, what you expected, what happened, and the trace id if
there is one.
