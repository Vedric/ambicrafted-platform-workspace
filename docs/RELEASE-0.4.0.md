# 0.4 delivery and qualification — 27 September 2026

The platform is qualified for a **private, local, supervised single-operator
workspace**. It is not yet approved as a commercial production service. The
container security gate still fails on **53 HIGH findings**, with zero CRITICAL
findings in the current seven-image inventory. A release candidate must retain
this limitation; passing functional tests is not a security waiver.

Application versions: console/control 0.4.0, speech 0.3.0. The tagged Git revision,
fresh-clone evidence and hosted CI results identify the delivered source; local
measurements below describe the qualification workstation, not portable SLOs.

## Delivered experience

- English/French interface, light/dark themes, larger text, responsive workspace,
  scroll entrances, pausable animation, keyboard access and reduced-motion support.
- Eighteen mission briefs covering SRE, DevOps, DevSecOps, platform/cloud/security
  engineering, FinOps and agent evaluation. These share a bounded supervised
  investigation workflow; they do not deploy an autonomous fleet to client systems.
- Seven operational chart panels, accessible data tables, token usage with explicit
  missing measurements, and five interactive architecture journeys. Animated arrows
  explain the design; they do not pretend to measure live traffic.
- AURA's saved conversations, searchable history, contextual continuation and
  explicit selected documents. Supported bounded extraction includes text/CSV,
  XLSX, DOCX, PPTX, text PDF and raster images; arbitrary file understanding and
  scanned-PDF OCR are not promised.
- Dedicated Neo4j notes and relationships, explicit source/scope selection and
  context transfer into a fresh conversation. A scope is not a tenant boundary.
- NEXUS is the common stdio MCP entry point, with fixed profiles: four runbook
  tools for the SRE agent, and those four plus eleven read-only control tools for
  the operator. No arbitrary shell, Cypher or approval tool is exposed.
- CLI conversation/document commands and the same authenticated analysis,
  maintenance, readiness and human-decision controls as the UI.
- Six locally hosted playable guide videos, written examples and annotated actual
  browser screenshots using synthetic demonstration data in the README.

## Voice and ambient audio

AURA addresses the operator as Védric, with French vouvoiement and conversational
wording. The shared multilingual ONNX synthesis model produces 24 kHz local audio;
trusted pronunciation rules handle English technical names inside French speech.
The weights, styles and phoneme vocabulary are pinned and hash-verified. This is
inference and pronunciation engineering, not a claim of training new model weights.

The public technology briefing refreshes every three days when the local service
is active. Fixed publisher feeds and a validated public cache supply its dated
sources. Briefings are bounded to fit speech output; the qualified welcome plus
briefing was approximately 90–105 seconds depending on language. First playback
may require a browser gesture. No browser autoplay policy is bypassed.

**Orbital Drift** is an original 96-second instrumental, generated without external
samples or a borrowed melody and dedicated under CC0. It starts only after an
operator choice, defaults to low volume, attenuates immediately during AURA or a
guide video, and becomes muted during microphone capture. It returns with a fade,
pauses in a hidden tab and stops with Escape. Speech has priority throughout.
Chromium playback and volume transitions are verified; physical output balance and
Safari-specific volume behavior still require device acceptance.

Synthetic mixed-language probes recovered GitHub Enterprise, Kubernetes, pipeline
and rollback after the pronunciation change. One workstation probe generated
10.4 seconds of French audio in 1.486 seconds and 9.05 seconds of English audio in
1.185 seconds. These are narrow measurements, not universal latency guarantees or
human listening scores. Speech remains bounded whole-response synthesis, without
full-duplex interruption. See [voice operation and licensing](VOICE.md).

## Verification

| Local suite or exercise | Result |
|---|---|
| Control API | 492 tests passed |
| SRE engine | 149 tests passed |
| Runbook MCP | 48 tests passed |
| Console unit tests | 218 passed across 19 files |
| Voice | 72 fast tests and 18 real model tests passed |
| Desktop/mobile Chromium | 50 Playwright journeys passed |
| Image scanner contracts | 11 tests passed |
| Static checks | Python lint/types; console types, formatting and production build passed |
| Real conversation | Local model, saved context, CSV calculation and image interpretation exercised |
| Real memory UI | Create, link, select context, converse and remove synthetic notes passed |
| SRE adversarial example | Conflicting symptoms and injected instruction reviewed; human gate preserved |
| Bounded read load | 240 authenticated requests, concurrency 8, all HTTP 200 |
| Restore drill | Disposable databases restored and compared successfully |

The restore checked seven analyses and seven checkpoints, zero restored
sessions/tickets, 86 PostgreSQL tables, 31 Qdrant points and valid SQLite files.
Graph restore includes full logical-content comparison; a separate populated
synthetic drill covered two notes and one link. Cross-database snapshots are not
atomic: quiesce mutations when continuity across stores is required.

Corrections found by these checks include a lost click when focus moved an
animating card, tablet header overflow, a speech phonemizer language mismatch,
oversized technology briefings and disposable Qdrant storage permissions. Failed
attempts are retained in private qualification evidence rather than counted as
successful tests. No finite suite establishes zero bugs or complete WCAG compliance.

## Security and production conditions

Tempo and Qdrant now have qualified derivatives with zero HIGH/CRITICAL findings.
Grafana retains nine HIGH findings in embedded libraries/plugins; Neo4j retains
44 in distribution packages. All seven images are scanned, package inventories
are retained, and no finding is suppressed. The exact counts and qualifications
are in [the security review](SECURITY-REFINEMENT-2026-09-27.md).

Before a commercial deployment:

1. Resolve or individually assess the remaining advisories with traceable decisions,
   qualify future upgrades/rollback and obtain an independent adversarial review.
2. Define supported hardware/OS/browser configurations and run a second-machine
   installation and physical audio acceptance. The current reference is Linux/WSL2
   with local models and sufficient GPU memory; arbitrary machines are not certified.
3. Isolate untrusted document parsing at the OS/container boundary. The current
   bounded subprocess is not an OS sandbox.
4. For a shared service, implement tenant isolation, RBAC/identity lifecycle,
   separate reviewer authority, secrets management and auditable retention rules.
5. Establish measured capacity, sustained load/soak tests, SLOs, recovery objectives
   and independent backup storage for the chosen deployment.
6. Review runtime redistribution/model/voice licensing for the intended offer;
   preserve the documented source and attribution obligations.

For client work today, use a dedicated qualified deployment per client, reviewed
runbooks and confidential local routing. Follow the [step-by-step mission
guide](CLIENT-WORKFLOW.md), [operations](OPERATIONS.md), [conversation and document
guide](CONVERSATIONS.md), [memory](MEMORY.md) and [MCP gateway](MCP-GATEWAY.md).

Open the welcome page at <http://127.0.0.1:8787/welcome>; use `./plateforme ouvrir`
from the checkout for a private one-use authenticated browser entry. No credential
belongs in a shared URL, screenshot, release or support report.
