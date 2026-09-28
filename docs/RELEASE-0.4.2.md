# Audio device selection and completion assessment — 28 September 2026

Console 0.4.2; control API 0.4.0 and speech runtime 0.3.1 unchanged.
This remains a private, local, supervised workspace. It is a release candidate,
not an approval for a commercial multi-user production service.

## Changes

AURA returns to a vertical instrument beside the conversation on wide screens,
stacking on smaller screens. Its centered visual, heartbeat, short entrances,
motion pause and reduced-motion support remain available.

**Audio devices** exposes input/output choices, explicit device detection, an
audible speaker test and a local microphone meter/recording/replay. It is available
on Welcome and in AURA. The optional voice-processing switch helps investigate
virtual inputs affected by echo cancellation or noise suppression. Permission
denial, busy input, disconnected devices and unsupported speaker selection have
recovery guidance. An explicit input choice never silently captures another mic.

Device preferences stay in browser storage. A shared routing module covers AURA,
Welcome, local diagnostics, music and guide videos, including output changes
during playback. Canceled permission/routing operations cannot start late capture
or playback. The system-default path does not depend on speaker-selection support.
See [the routing ADR](adr/0027-browser-audio-routing.md).

The English/French voice walkthroughs now demonstrate device detection. The
recordings use disposable synthetic data; narration is generated locally.
Follow the [audio setup guide](CONSOLE.md#microphone-sound-and-walkthroughs).

## Verification boundaries

Working-tree checks passed 239 UI unit tests, 68 desktop/mobile Chromium journeys,
six media asset checks and npm audit with zero reported vulnerabilities. Eight
viewport/theme combinations passed overflow and automated accessibility checks.
Qualification also covers TypeScript, formatting and the production build. Browser
journeys include permissions, device removal, remembered choices, exact input
constraints, native recording/replay, shared output routing, video decoding,
authentication, navigation, both languages and automated accessibility checks.
Clean-checkout results and hosted CI identify the exact qualified commit.

Device inventory and selected-output identifiers are synthetic in browser tests.
The browser really records, decodes and plays audio, but its virtual output adapter
uses the native default sink. These tests do not prove that a particular Windows
microphone captures speech or that a physical headset emits sound. Human listening
and real-device acceptance are still required. The UI cannot override OS mute,
browser permission, audio drivers or unsupported APIs.

## What is still needed to finish

For a dependable private daily workspace, prioritize these acceptance gates:

| Priority | Remaining work | Evidence required to close it |
|---|---|---|
| 1 | Physical audio and installation portability | Actual microphone/headset conversation in FR/EN, denial/reconnect recovery, supported browser matrix, fresh installation on a second machine |
| 2 | Container security | Re-scan pinned images; remediate or assess each remaining finding with a traceable decision and tested rollback |
| 3 | Real engineering workflows | A few end-to-end client-safe SRE, DevOps and security exercises with verified sources, approval boundaries, repeatable evaluations, latency and token/cost budgets |
| 4 | Operational resilience | Sustained load/soak measurements, chosen SLOs and capacity, off-host backups, measured restore/RPO/RTO and upgrade/rollback drills |

The 27 September container assessment reported **53 HIGH findings** (44 Neo4j,
nine Grafana) and zero CRITICAL findings across seven images. Those are dated
results, not a new scan or a waiver. Consult [the security assessment](SECURITY-REFINEMENT-2026-09-27.md).

The 18 mission presets currently feed the same bounded, supervised SRE analysis
graph. They provide useful briefs; they do not constitute 18 independently
qualified specialist agents. Conversation does not execute remediation. Extend
the tools and workflows against concrete acceptance cases rather than enabling
every MCP server or granting agents broad execution authority.

Before commercial or shared deployment, additional gates apply:

- Isolate untrusted document parsing at the OS/container boundary; the current
  bounded subprocess is not an OS sandbox.
- Implement and adversarially verify tenant isolation, RBAC/identity lifecycle,
  separate reviewer authority, secrets management and retention/deletion rules.
- Commission an independent security review of the actual deployment, including
  agent tool authorization, prompt injection and recovery paths.
- Review redistribution and model/voice licenses for the intended offering, then
  define support scope, deployment requirements and measurable service commitments.

No finite test suite establishes zero bugs or zero vulnerabilities. A clear set
of passed acceptance gates is a defensible definition of completion. The existing
[0.4 assessment](RELEASE-0.4.0.md) and [client workflow](CLIENT-WORKFLOW.md) remain
the operational baseline until these gates have evidence.
