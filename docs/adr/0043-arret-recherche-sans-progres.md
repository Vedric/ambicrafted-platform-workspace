# ADR 0043 — Stop source exploration after demonstrated non-progression

Date: 2026-10-21

Status: Implemented; new frozen-source model qualification required

## Context

The frozen twelve-case evaluation of the bounded consistency review retained
five mechanical contracts and encountered three budget-exhausted runs after
repeated searches or reads. Increasing budgets would pay for more repetition
without proving better conclusions. These twelve cases become regressions after
this change; their original results and expectations remain intact. A new holdout
and substantive review are still required. Unit tests and an AI reviewer do not
constitute human acceptance.

Until now both engines declared tools on every reasoning turn. That rule prevents
silently bypassing an exhausted tool budget by delivering a degraded diagnosis.
It does not distinguish useful new evidence from repeated consultation of the
same source. This decision introduces a narrowly defined stopping policy for the
latter, without raising or resetting any existing ceiling.

## Decision

Both engines share a small deterministic tracker. Its only evidence of progress
is a previously unseen pair of filename and SHA256 of the content in the verified
read registry. That registry is still populated exclusively by complete read
envelopes with correct filenames and content digests. A search result, malformed
envelope, paraphrase or model declaration cannot populate it.

The first verified read starts tracking. A new pair resets the consecutive
non-progress counter. Two complete tool turns without any new pair request
finalisation on the next reasoning turn. Several tools requested in one turn
count as one turn. A file's new content version counts as progress; alternating
back to a previously seen version does not. The state is bounded by the existing
number of tool calls, and contains only source names and digests beyond the
already retained source registry.

Finalisation makes one local confidential call under the same observed-token,
money, deadline, context and turn limits. It receives no tool declarations and
an explicit instruction that the existing evidence may be incomplete. Its strict
schema permits the ordinary five proposed diagnostic fields only. Application
review data (`qualite`), invented source registries and extra fields are rejected
by code even if the provider ignores the generation schema. A returned tool call
is refused without execution. Invalid finalisation has no retry, tool reopening
or partial diagnosis fallback.

This replaces the earlier always-declare-tools policy **only after actual
verified reads followed by demonstrated stagnation**. Exhaustion alone never
activates it. No verified read means no forced diagnosis. A ceiling reached
before finalisation or review remains budget exhaustion, with no partial answer
presented as complete.

The resulting proposal still passes the unchanged source guard, bounded AI
consistency review and, for the graph, durable human approval. These gates may
remove actions, lower confidence or cause abstention. The finalisation cannot
write new proof to the read registry, change budgets or supply its own successful
review. The `llm.finalisation_recherche` span distinguishes this call from ordinary
reasoning; existing token/call/latency accounting remains authoritative.

## Alternatives rejected

- Larger tool/turn/token limits: they do not address repetition.
- Business keyword rules or per-evaluation-case exceptions: they would encode
  expected answers instead of enforcing a general progress invariant.
- A cache alone: it can reduce MCP cost while retaining expensive LLM turns and
  repeated context. This decision does not cache or fabricate tool responses.
- A second planning agent or progress judge: it adds model cost and an additional
  fallible decision when a code-owned source identity is sufficient for this
  narrower stopping policy.
- Dropping tools whenever any budget is exhausted: that would conceal the reason
  for a degraded result and weaken the pre-existing limits.

## Consequences and limitations

Search snippets are discovery candidates, not verified source reads. A genuinely
useful exploration requiring several searches before another read can therefore
stop early. Two no-progress turns are an explicit resource policy, not a theorem
that more research would be useless. Newly retrieved sources may also be irrelevant
despite their new hashes. The tracker establishes neither sufficiency nor semantic
truth; the same-model reviewer may still miss errors or reject useful proposals.

The graph retains only names/digests and counters in its checkpoint. The original
alert remains invocation-only under the existing confidentiality contract. The
ordinary loop and graph keep their documented difference for oversized tool
batches: the graph refuses a batch before entering its tool node, while the loop
checks each individual call.

Tests exercise both engines through real budget/source/review boundaries, replacing
only external HTTP/MCP responses. They cover repeated reads, multi-tool turns,
new files, new and previously seen versions, search-only results, invalid envelopes,
unchanged ceilings, provider-ignored schemas, forbidden tool calls and review
abstention. Existing recursion tests now supply genuinely changing verified source
versions so they still reach ten and twenty-six tool calls; their success criteria
were preserved or strengthened, not relaxed to accept the new stopping condition.

The next model qualification must report usefulness, abstention, failures,
observed tokens and latency separately, preserving the earlier baseline. Reduced
cost or a clean schema is not evidence of factual correctness. Independent human
review remains outstanding.
