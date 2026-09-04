# ADR 0008: the staged diff leaves the machine for GitGuardian's API

Status: accepted
Date: 2026-09-04

## Context

The `ggshield` pre-commit hook (`.pre-commit-config.yaml`) refuses a commit
whose staged diff contains a recognisable secret. It does not detect locally:
it **sends the staged diff to GitGuardian's API** at every commit and acts on
the answer. Version 1.54.0 offers no offline mode — verified, there is no such
option on `ggshield secret scan`. Installing that hook therefore opens an
outbound data flow, and under rule 2 a data flow is decided, not discovered.

This ADR exists because the reasoning that made the flow acceptable was made
in conversation, and would otherwise have stayed there. An assumption nobody
writes down is an assumption nobody remembers having made, so it is never
re-examined when the ground moves.

## Decision

The flow is accepted. `ggshield` runs against GitGuardian's API on every
commit.

The argument rests on two facts, both load-bearing:

1. **GitGuardian already receives this repository's content.** Its GitHub
   integration reads what is pushed. Verified rather than assumed: the two
   incidents of 2026-08-27 were raised within minutes of the push
   ([`SECURITY.md`](../../SECURITY.md)). Sending the same content a few
   seconds earlier, over the API instead of over the integration, exposes it
   to nobody who was not already going to receive it.
2. **No client data is in this repository.** Rule 2 keeps mission logs,
   configurations and client code out of it entirely; those workloads run on
   the `local` alias through the `confidential-only` virtual key and never
   reach a versioned file. What is here is platform code, documentation and
   placeholder templates.

Neither fact is a claim that `ggshield` is trustworthy. They are claims about
the content: in both cases, content GitGuardian was going to see anyway.

**The delta, stated honestly.** It is not zero. A diff that is refused, or
amended, or committed on a branch that is never pushed reaches the API
without ever reaching GitHub. What GitGuardian sees is therefore a superset
of what the integration alone would show it. That superset is made of this
repository's own material, so fact 2 covers it — but it is a difference, and
calling it zero would be wrong.

**One consequence observed while testing the hook.** GitGuardian does not
only pattern-match. A fake AWS key pair staged on 2026-09-04 came back
`Validity: Invalid`, meaning the credentials were **tested against AWS**. A
secret that reaches a staged diff is a secret a third party tries. This does
not change the existing rule, it sharpens it: after any exposure, rotate.

## What would invalidate this

Either fact can stop being true, and neither failure announces itself. This
section is the reason the ADR is worth writing at all.

- **The repository becomes public.** Fact 1 stops being the argument it was.
  Contributors from outside this machine would run the hook and send *their*
  staged diffs, not ours, to our GitGuardian workspace under a token we
  issued, with the incidents landing on our dashboard. The confidentiality
  question dissolves and a different one takes its place. To be re-examined,
  not assumed to have become easier.
- **Client data enters the repository.** Fact 2 falls, and rule 2 with it.
  The flow would have to go, or the data would. A path exclusion in
  `.gitguardian.yaml` would **not** be an answer: it configures `ggshield`
  alone, and the GitHub integration, which does not read that file, would go
  on reading the file anyway.
- **The GitHub integration is removed, or its scope changes.** Fact 1 falls
  entirely: the API call stops duplicating an existing flow and becomes the
  only one. This is the condition most likely to change in silence, because
  removing a dashboard integration feels like *reducing* exposure — which is
  precisely when this ADR needs re-reading.

## Alternatives rejected

- **A purely local scanner** (`gitleaks`, `detect-secrets`). It removes the
  flow and removes most of the reason to have the hook: the detector set, its
  upkeep and the validity checks are what GitGuardian provides. A weaker
  detector would buy the same feeling of coverage for less coverage — the
  failure mode ADR 0007 already names.
- **No pre-commit hook, the dashboard alone.** That was the situation before,
  and it is detection after the push: by the time the alert arrives the value
  is in the history, in every clone and in every mirror, and rotation is the
  only remedy. Closing that window is the entire point.
- **The hook in CI only.** The diff leaves the machine either way, so the
  flow is unchanged, and the refusal arrives after the push. All of the cost,
  none of the benefit.

## Consequences

- **Every commit now needs GitGuardian reachable and the token valid.** A
  network outage or an expired token refuses the commit; the hook does not
  skip itself. That is intended, and it is a real availability cost paid on
  purpose.
- One more secret to hold and rotate: `GITGUARDIAN_API_KEY` in the root
  `.env`, `scan` scope, with an expiry. It buys nothing else, and its expiry
  is a scheduled outage of the commit path unless it is watched.
- One API round-trip added to every commit.
- A third party now sits in the path of every commit on this machine. That
  supply-chain surface is bounded by rule 7 and no further: the revision is
  pinned to the one actually in service (`ggshield 1.54.0`, read from the
  hook's own environment, not from what the registry offers under a
  neighbouring name).
