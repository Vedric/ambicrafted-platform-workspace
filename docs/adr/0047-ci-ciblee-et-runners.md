# ADR 0047 — Targeted manual image audits and runner restraint

Date: 2026-10-21. Status: accepted.

## Context

The operator explicitly requested deliberate CI use and evaluation of self-hosted
runners. After billing admission was restored, rerunning the existing candidate
found a new HIGH advisory in Qdrant's dashboard build dependencies. Rebuilding
every unaffected image for each targeted correction wastes compute; treating a
partial audit as a complete release gate would weaken qualification.

## Decision

Allow a direct manual image audit to choose one service from a fixed matrix map.
Default to all eight images. Unknown values fail matrix validation rather than
entering shell commands. Check both event and caller workflow name: scheduled
audits and calls from Qualified release always use the full inventory, even
when the release itself was started manually. This supplements ADR 0037 without
changing its publication gate, scanner threshold or evidence requirements.

Bound ordinary jobs explicitly and allow the console 25 minutes after an observed
successful 19m35 run nearly exhausted its former 20-minute ceiling. This avoids
the default six-hour ceilings and gives normal browser setup variability room
without an automatic retry. Existing speech and image ceilings remain unchanged.

Keep standard GitHub-hosted runners. Revisit self-hosting only with measured cost,
queueing or hardware needs; use dedicated disposable VMs if justified. Do not
expose the running platform host or client data to general-purpose CI jobs.
Record the operator preference in workspace instructions and scoped memory.

## Alternatives rejected

- Repeated full audits for a single changed dashboard add no targeted evidence
  about unchanged build inputs, while increasing cost and feedback time.
- Letting a caller narrow release coverage would make a green draft ambiguous.
- Interpolating input into JSON or shell text introduces avoidable injection risk.
- Installing a persistent runner on the live workstation shares credentials,
  storage and privileged container access with workflow code.
- Changing or suppressing the failed tag's findings would destroy provenance.

## Consequences

Manual partial runs need explicit scope attribution; they do not certify a release.
The manual-selection guard depends on the workflow name. A rename must update
the guard; otherwise coverage expands safely to all images. The static map must
stay aligned with the declared image inventory. A future self-hosted deployment
requires a separate design, including replacement of hosted-only SDK cleanup.
Rerun existing jobs only after diagnosing and addressing their failure. See
[CI operations](../CI.md) for the invocation and evidence contract.
