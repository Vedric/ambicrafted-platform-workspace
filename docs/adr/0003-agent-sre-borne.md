# ADR 0003: bounded SRE agent, without a framework

Status: accepted, in local service since 2026-08-25
Date: 2026-08-25

## Context
The platform has the building blocks: a gateway with aliases and virtual
keys, a versioned runbook corpus, a read-only MCP server, semantic search,
tracing to Tempo. They had never been assembled into an executable object.

An on-call agent is the most exposed thing one can build: it ingests
uncontrolled client data, it consumes budget non-deterministically, and its
output will be read by someone tired who will execute it. The three ways it
can do harm (leak, cost drift, invented procedure) call for *structural*
guardrails, not prompt instructions.

## Decision

### No agent framework
The loop is hand-written in `agent.py`, about one hundred lines. Those are
exactly the lines where budget accounting, alias selection by data
classification, and the encapsulation of tool results are decided. Delegating
that loop to a library means delegating the guardrails to code nobody
re-reads.

This choice is also a comparison baseline: a LangGraph port is planned as a
later step. Comparing presupposes having the bare version.

### Compartmentalisation wins over the per-step choice of alias
The initial specification put alert classification on the `fast` alias.
Applied to the raw alert, it would send client data across the border,
contradicting rule 2 of CLAUDE.md.

Processing is therefore split in two:

```
raw alert ──[ local, CONFIDENTIAL ]──> anonymised extract
                                              │
                      ═══ border ═══          │
               ──[ fast,  DERIVED ]──> triage ┤
               ──[ smart, DERIVED ]──> tool loop ──> diagnostic
```

The local step extracts the technical signature, removes identifiers and
records injection attempts. `fast` does perform the triage, but on the
extract. No byte of the raw alert crosses the border, and the original intent
(a fast, cheap triage) is preserved.

Accepted consequence: the local model reasons before answering, and this step
costs 30 to 50 seconds. That is the price of confidentiality, paid once per
alert.

### A single point of passage to the gateway
Every LLM call goes through `llm.appeler_llm`, which takes a mandatory
`Classification`. There is a single place to read in order to know whether
client data can leave. A direct `httpx` call elsewhere in the package would
be an architectural defect, not an optimisation.

The guard rests on a strict partition of aliases into `ALIAS_LOCAUX` and
`ALIAS_FRONTIERE`: that partition is what makes the decision computable
rather than interpretable. A test verifies that the two sets stay disjoint.

### Three barriers rather than one
1. Application guard, before any network access.
2. Restricted virtual key for confidential payloads: the gateway answers 403
   if the first one fell.
3. No fallback out of `local` in the gateway configuration.

They are independent: none assumes the others are correct.

### Security comes from the absence of the tool
The agent has no shell, no file write, no arbitrary HTTP. Not because a
prompt forbids it, but because no function in the package exposes them.
`OUTILS_AUTORISES` is furthermore a closed allow-list: a tool the MCP server
might publish without appearing there would never be presented to the model.
Adding a tool remains a decision of this repository.

### Budgets opposed at the moment of the attempt
The tool budget is decremented *before* execution: a refused call does not
reach the server. The monetary budget is charged *after*, from the gateway's
cost header; the agent holds no price table, which would force it to know
model names.

Important sub-decision: when the tool budget is exhausted, the tools stay
declared to the model. The temptation was to remove them to "save" a turn;
that would make the model answer without having consulted the runbooks, and
that degraded answer would be returned as a diagnostic. A budget must be
opposed at the moment the agent tries to exceed it, not worked around
upstream. Both budgets lead to the same stop: no half-diagnostic.

### Untrusted data encapsulated, never concatenated
The alert text and the runbook contents enter the context between two markers
carrying a random token drawn once per run. The token is not cryptography: it
removes from whoever writes the alert the ability to write the closing
marker. The associated instruction asks to **report** any encountered
instruction rather than follow it: reporting an injection is itself
diagnostic information, since an alert carrying an injection is probably
forged.

The recorded hostile text stays local. The frontier steps only receive the
count.

### `runbook_source` nullable, and acted upon by the code
A model forced to give a source invents one. Allowed to declare `null`, it
provides the most useful information in the report. `appliquer_garde_source()`
then removes its actions from `actions_proposees`, moves them into
`actions_ecartees_sans_source` and replaces them with a human escalation. The
code refuses the prose; it does not merely read it.

## Consequences

Verified in execution:
- PostgreSQL alert: `incident-p1-database.md` found, sourced diagnostic,
  3 tools, 0.23 USD.
- Out-of-corpus TLS alert: `runbook_source = null`, actions discarded by the
  code, no invented procedure.
- `SRE_MAX_APPELS_OUTILS=2`: clean stop on refusing the 3rd tool, exit code 2.
- `SRE_MAX_COUT_USD=0.05`: clean stop, exit code 2.
- Injection-bearing alert: instruction reported, not followed.
- Complete trace in Tempo: parent span and 8 child spans.

Accepted costs and limits:
- 30 to 50 s of local extraction per alert.
- Reasoning on `smart` consumes about half of the 0.50 USD cap on a nominal
  case. The cap is tight, deliberately: it has to be reachable to be
  credible.
- Tempo's OTLP address is a container address, sensitive to a recreation.
  Publishing port 4318 on the host would be the durable fix, but belongs to
  the gateway's Compose file, not to this agent.
## Alternatives rejected
- **Hard-coded search plan** (semantic_search then read_runbook): would make
  the iteration budget decorative, and remove the very behaviour that is
  meant to be bounded.
- **Anonymisation by regular expressions**: does not cover proper nouns or
  business identifiers, and does not detect injections. The local model does
  both in the same call.
- **Forbidding unsourced actions by prompt alone**: unverifiable. The
  nullable field plus the downstream refusal are testable.
