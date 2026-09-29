# Personal workspace refinement — 0.4.5

Console **0.4.5**, control API **0.4.2**, speech runtime **0.3.2**.
This remains a release candidate for a private, single-operator workstation.
It is not a zero-defect or commercial production certification.

## Delivered behavior

AURA reuses a private local speech worker between turns. Model hashes and
recognition settings remain unchanged; warm reuse reduces startup work. The
worker has bounded input/output, correlated responses, cancellation cleanup and
a five-minute idle exit. The standalone CLI remains usable. On this workstation,
a fixed French sample went from 5.61–5.85 s transcription to 3.49–3.57 s on warm
turns; its short synthesis went from 1.84–1.98 s to 0.67–0.70 s. These small tests
exclude recording, LLM generation and playback; cold startup still exists.

Input/output now follow OS defaults throughout AURA, Welcome, videos and music.
Explicit device pickers are removed and older browser selections are ignored.
The local microphone diagnostic, permission recovery, manual transcription review
and hands-free stop controls remain. Music continues yielding to speech/capture.

The shared vector emblem is redesigned and enlarged. Overview uses a balanced
grid and a larger animated instrument. The vertical AURA layout remains. Guide
cards now align across columns instead of leaving a large empty area. Existing
scroll reveals and motion preferences are preserved. Light-theme contrast is
corrected for the hero link and central emblem. The six narrated guide videos
and annotated portfolio screenshots are regenerated from the disposable UI.

The observability page links to three Grafana views in both languages. Dashboards
cover service health, collection freshness, retained work, SRE usage coverage,
API/voice latency, queue, Linux/GPU resources and backups. The private collector
does not expose credentials or client content to monitoring. Missing/stale data
is distinguished from healthy zero activity. Alert rules include recovery tests.
See [Monitoring](MONITORING.md) for installation, interpretation and operation.

## Qualification and evidence

The release process uses a fresh checkout and the exact qualified commit, with
hosted CI, Python tests/lint/types/builds/audits, console tests and native
Playwright desktop/mobile/Firefox motion checks. The tagged release's evidence
records the final counts and commit; an earlier working-tree run is not its CI
proof. The strict image-security result remains separate and failed.

Additional local checks include:

- 23 real French/English speech and codec checks in a network-isolated namespace,
  including repeated turns through the resident worker.
- Twenty-four responsive page views at 390, 768, 1440 and 1920 pixels, in both
  themes/languages, with no detected horizontal overflow or JavaScript exception.
- Six native Grafana views, with the upgraded plugins accepted as signed by
  Grafana itself; PromQL validation and freshness/failure rule tests.
- A new backup/isolated restore drill covering console/checkpoints, PostgreSQL,
  Qdrant, Grafana and graph memory. Sessions and login tickets are absent from the
  restored console. This is not one atomic cross-database snapshot.
- Four real local-model contract evaluations: abstention without evidence,
  instruction injection and exact quoted source/action handling. All four passed,
  consuming 1,046 reported tokens in approximately 11.2 seconds in this small run.
  This does not establish general SRE reasoning accuracy.

Raw local evidence is outside Git under
`/home/vedric/platform/final-closure-2026-09-29/`. Public screenshots and videos use
synthetic data; they demonstrate the interface, not production incident quality.

## Remaining personal acceptance

1. Listen to AURA on the actual microphone/speakers and test a few natural French
   and English exchanges. Browser automation cannot certify physical audio quality
   or whether pronunciation sounds natural to the operator.
2. Keep a private off-machine backup and rehearse recovery there. A second physical
   machine, its browser permissions, CPU/GPU and drivers still need acceptance.
   Clean-checkout tests do not establish universal hardware portability.
3. Track the remaining image findings: **0 CRITICAL, 50 HIGH**, including six in
   Grafana and 44 in Neo4j. The [dated security report](SECURITY-2026-09-29.md)
   explains the corrections and open patch/applicability work. No waiver is added.
4. Review real mission outputs against your own curated evidence. Mission presets
   share the supervised SRE workflow; they do not create independent expert agents
   capable of arbitrary production remediation.

Long-duration workstation soak testing, physical browser/audio acceptance and
off-host recovery remain separate from automated regression coverage. Before
commercial use, add a reviewed tenancy/identity design, independent roles, audit
and data-processing requirements, stronger untrusted-file isolation, operational
SLOs and an explicit supported-hardware/deployment matrix. Follow the
[client workflow](CLIENT-WORKFLOW.md) for today's isolated personal deployments.

The project can be presented as an engineering portfolio with the supplied
synthetic screenshots and a factual account of its boundaries. Do not advertise
it as vulnerability-free, universally portable, or autonomously managing client
production. Keep client material, configuration secrets and private backups out
of public demonstrations.
