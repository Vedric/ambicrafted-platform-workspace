# Architecture Decision Records

Every architecture decision in this platform is recorded here (rule 5 of
[`CLAUDE.md`](../../CLAUDE.md)). An ADR is a **dated document that freezes a
decision** in the state of knowledge of its day: it is not updated when
reality moves on. When a decision is superseded, a new ADR says so and the
old one stays as it was written.

File names are kept in French, like every other identifier in this repository,
see the language policy in [`CONTRIBUTING.md`](../../CONTRIBUTING.md).

| # | Title | Status | Date | In one line |
|---|---|---|---|---|
| [0001](0001-litellm-passerelle-unique.md) | LiteLLM as the single gateway | Accepted, in local production | 2026-08-24 | One OpenAI-compatible entry point, semantic aliases, virtual keys, and no fallback out of `local`. |
| [0002](0002-recherche-semantique-runbooks.md) | Semantic search over the runbooks (Qdrant + MCP) | Accepted, in local service | 2026-08-25 | Chunk by markdown section rather than by character count, because a fragment of a procedure looks complete and is dangerous. |
| [0003](0003-agent-sre-borne.md) | Bounded SRE agent, without a framework | Accepted, in local service | 2026-08-25 | A hand-written loop, because the hundred lines it occupies are exactly the lines where the guardrails are decided. |
| [0004](0004-langgraph-vs-boucle-maison.md) | LangGraph against the hand-written loop | Accepted, both coexist, `agent.py` is the reference | 2026-08-25 | Measured: orchestration gains 50 ms and costs 23 packages; what you actually buy is a pause that survives `kill -9`. |
| [0005](0005-propagation-contexte-trace.md) | Propagation of the trace context to the gateway | Accepted | 2026-08-25 | One `traceparent` header turns two disjoint traces per call into a single 52-span trace per alert. |
| [0006](0006-stack-passerelle-dans-le-depot.md) | The gateway stack lives in the repository | Accepted | 2026-08-25 | The most critical layer existed only on disk; a clone plus a `.env` must be enough to rebuild it. |
| [0007](0007-secret-fuite-par-la-sortie.md) | A secret leaks through a command's output | Accepted | 2026-08-27 | The incident that rotated four secrets: nothing was written anywhere, the values were merely printed. |
| [0008](0008-diff-indexe-vers-l-api-gitguardian.md) | The staged diff goes to GitGuardian's API | Accepted | 2026-09-04 | An outbound flow accepted because GitGuardian already reads the pushed repository, written down with the two conditions that would take that argument away. |
| [0009](0009-garanties-verifiables-apres-audit.md) | Verifiable guarantees after the audit | Accepted; supersedes affected guarantees in 0002–0005 | 2026-09-26 | Local SRE pipeline, verified source paragraphs, refusal semantics, atomic indexing and operational recovery. |
| [0010](0010-console-et-plan-de-controle.md) | Private console and shared control plane | Accepted | 2026-09-26 | Authenticated UI/CLI, bounded jobs, human decisions and operator tools. |
| [0011](0011-voix-locale-et-outils-de-controle.md) | Offline voice and explicit control tools | Accepted | 2026-09-26 | Feminine French voice, local transcription, ephemeral conversation and read-only control MCP. |
| [0012](0012-images-correctives-verifiees.md) | Verified corrective container derivatives | Accepted | 2026-09-26 | Narrow pinned Qdrant/PostgreSQL rebuilds, isolated recovery tests and visible residual findings. |
| [0013](0013-voix-anglaise-reactive.md) | English default voice with explicit French selection | Accepted | 2026-09-27 | Offline English/French female speech, selected-language recognition and local AURA dialogue. |
| [0014](0014-readiness-et-outils-locaux.md) | Measured local readiness and read-only operator MCP | Accepted | 2026-09-27 | Evidence-based local checks shared by UI/CLI/MCP and a bounded nine-tool control surface. |
| [0015](0015-experience-immersive-bilingue.md) | Immersive bilingual workspace and supervised voice interaction | Accepted | 2026-09-27 | Shared EN/FR interface, mission intake and opt-in AURA conversation within the existing local boundary. |
| [0016](0016-maintenance-dependances-et-postgresql.md) | Coordinated dependency updates and explicit PostgreSQL migration | Accepted; major database migration deferred | 2026-09-27 | Coherent Python locks, pinned Node 22 and tools; PostgreSQL 16 retained until a qualified data migration. |
| [0017](0017-indicateurs-flux-et-defilement.md) | Operational charts, architecture paths and scroll accents | Accepted | 2026-09-27 | Real run/probe data, conceptual component flows and bounded, accessible motion. |
| [0018](0018-provenance-des-dependances-locales.md) | Preserve local dependency provenance in automated updates | Accepted; release qualification recorded separately | 2026-09-27 | Ignore only the local agent's public homonym while qualifying the runbooks dependency updates. |
| [0019](0019-provenance-recherche-console.md) | Reject stale semantic results at the console boundary | Accepted | 2026-09-27 | Verify current source snapshots and exact indexed passages before returning console search results. |
| [0020](0020-backend-vocal-reproductible.md) | Pin the qualified speech compute backend | Accepted | 2026-09-27 | Select oneDNN before native import and retain fixed-signal regression assertions across fresh CLI processes. |
| [0021](0021-reconnaissance-anglaise-dediee.md) | Bound dedicated English recognition to short turns | Accepted; exact release qualification recorded separately | 2026-09-27 | Use dedicated English weights within one acoustic window and preserve the existing long-recording and French paths. |
| [0022](0022-passerelle-mcp-locale.md) | One local MCP gateway and measured usage budgets | Accepted; private local scope | 2026-09-27 | NEXUS routes bounded read-only profiles; ATLAS keeps four tools and reports usage coverage honestly. |
| [0023](0023-conversations-voix-et-memoire.md) | Local conversations, speech and explicit graph context | Accepted for local private scope | 2026-09-27 | Bounded saved dialogue, document extraction, default audio and scoped operator memory. |
| [0024](0024-veille-technologique-publique.md) | Cached public technology watch | Accepted for local private scope | 2026-09-27 | Fixed public feeds, local bilingual summaries, dated sources and a 72-hour refresh cycle. |
| [0025](0025-voix-conversationnelle-et-ambiance.md) | Conversational voice and subordinate ambient audio | Accepted | 2026-09-27 | Multilingual local synthesis, technical phonemes, an original score and explicit audio priority. |
| [0026](0026-precision-reconnaissance-francaise.md) | French recognition precision | Accepted | 2026-09-28 | Preserve French words with float32 inference and fixed cross-CPU regression audio. |
| [0027](0027-browser-audio-routing.md) | Browser-local audio routing | Superseded by 0031 | 2026-09-28 | Explicit device selection at the time; system defaults restored in 0031. |
| [0028](0028-reactivite-conversation-et-mouvement.md) | Conversation responsiveness and continuous motion | Accepted | 2026-09-28 | Bounded spoken turns, cancellation and visible motion. |
| [0029](0029-preferences-mouvement-explicites.md) | Explicit motion preferences | Superseded by 0048 | 2026-09-29 | Shared motion state with an explicit operator override. |
| [0030](0030-observabilite-privee.md) | Private operational telemetry | Accepted | 2026-09-29 | Aggregate collection, bilingual Grafana and freshness-aware alerts. |
| [0031](0031-moteur-vocal-resident.md) | Warm local voice and system audio defaults | Accepted | 2026-09-29 | Resident speech worker; supersedes routing in 0027. |
| [0032](0032-isolation-systeme-des-documents.md) | OS-enforced document extraction | Accepted for private Linux/WSL | 2026-10-20 | Rootless namespaces, read-only parser filesystem and native syscall policy. |
| [0033](0033-recuperation-privee-verifiable.md) | Verifiable private recovery | Implemented | 2026-10-20 | Source inventory, encrypted export and nonempty restore drills. |
| [0034](0034-qualification-agentique-et-cycle-de-vie.md) | Separate workflow and lifecycle qualification | Accepted | 2026-10-20 | Real local graph/MCP scenarios and separate expert review. |
| [0035](0035-neo4j-memoire-ubi10.md) | Dedicated Neo4j memory profile | Qualified separately | 2026-10-20 | Vendor UBI10 runtime, explicit Parquet exclusion and logical rollback. |
| [0036](0036-grafana-source-et-plugins-signes.md) | Grafana rebuild and official signed plugins | Affected choice superseded by 0042 | 2026-10-20 | Pinned core remediation with original official plugin signatures. |
| [0037](0037-maintenance-images-et-verrou-release.md) | Corrective images and release gate | Accepted | 2026-10-20 | Source-verified derivatives and publication gated by CI and image security. |
| [0038](0038-observations-originales-et-sorties-contraintes.md) | Original observations and constrained output | Implemented; semantic limits remain | 2026-10-20 | Ephemeral original observations retained across triage and final reasoning. |
| [0039](0039-selection-volumes-reprise.md) | Explicit volume selection for recovery | Accepted | 2026-10-20 | Private volume selection separates candidate promotion from rollback data. |
| [0040](0040-artefacts-conversation-locaux.md) | Typed local conversation artifacts | Implemented; qualification recorded separately | 2026-10-20 | Bounded diagrams/reports, atomic history, local exports and explicit memory drafts. |
| [0041](0041-revue-coherence-agent-bornee.md) | Bounded agent consistency review | Implemented; qualification recorded separately | 2026-10-21 | Exhaustive proposition references, rejection-only review and absolute HTTP deadline. |
| [0042](0042-distribution-grafana-privee-corrigee.md) | Minimal Grafana distribution with bounded private signatures | Candidate qualification | 2026-10-21 | Only required corrected plugins, exact compiled manifest trust and real loader refusals. |
| [0043](0043-arret-recherche-sans-progres.md) | Bound repeated source exploration | Implemented; qualification recorded separately | 2026-10-21 | One structured finalisation after two rounds without new verified source identities; budgets unchanged. |
| [0044](0044-retrait-cible-racine-emsign-g3.md) | Exact emSign ECC G3 distrust across runtime trust stores | Accepted for the candidate; deployment is separate | 2026-10-21 | Exact-root distrust with preserved unaffected roots, package inventories and native trust verification. |
| [0045](0045-arret-stdio-mcp-annulable.md) | Cancellable local MCP stdio and backend cleanup | Accepted | 2026-10-21 | Bounded cancellable transport, descriptor ownership and same-task backend cleanup. |
| [0046](0046-diagnostic-erreurs-documents.md) | Safe document failure diagnostics | Accepted | 2026-10-21 | Finite typed categories and private operation correlation; acceptance and model quality unchanged. |
| [0047](0047-ci-ciblee-et-runners.md) | Targeted manual image audits and runner restraint | Accepted | 2026-10-21 | Manual allowlisted service selection; full scheduled/release inventory and isolated runner policy. |
| [0048](0048-observabilite-correlee-et-mouvement.md) | Correlated local observability and automatic motion | Implementation; qualification separate | 2026-10-21 | Observed seven-day objectives, bounded RUM/traces, explicit log limits and OS accessibility. |
| [0049](0049-paquet-ca-wolfi-natif.md) | Native Wolfi trust package correction | Qualified locally; hosted release and deployment separate | 2026-10-22 | Signed package, complete CA-bundle identity and real native trust checks. |
| [0050](0050-recherche-utile-et-correction-non-retenue.md) | Useful source exploration; decline unproven automatic repair | Clarification retained; repair not adopted | 2026-10-22 | Separate missing observations from missing procedures; retain failure evidence and human review. |
| [0051](0051-deploiement-personnel-hybride.md) | Qualified hybrid personal deployment | Accepted for the private Linux workstation | 2026-10-22 | Eight containers plus native supervised application; public source without public ingress. |
| [0052](0052-correctifs-images-compatibles.md) | Compatible image corrections beyond the blocking threshold | Qualified personal profile | 2026-10-22 | Native package signatures, aligned runtime dependencies, complete trust stores and explicit residual findings. |
| [0053](0053-retroportage-tracestate-litellm.md) | OpenTelemetry correction within supported dependency graphs | Source/MCP and targeted gateway profile qualified; generation blocked | 2026-10-23 | Official MCP API update and pinned upstream gateway backport; retained scanner findings and separate evidence. |

## Reading order

- **Current behavior**: 0009–0053, then the current README and security document;
  the dated records remain unchanged when implementation evolves.
- **Operating the current workspace**: [console guide](../CONSOLE.md),
  [local tools](../TOOLS.md), [MCP gateway](../MCP-GATEWAY.md), [voice](../VOICE.md) and
  [client mission walkthrough](../CLIENT-WORKFLOW.md).
- **Historical context**: 0001 (the gateway), then 0003 (the agent), then
  0002 (the RAG pipeline).
- **Interested in the security argument**: 0003, then 0007, then 0008, then
  [`SECURITY.md`](../../SECURITY.md). 0007 and 0008 read together are the
  point: the first says no hook can see a command's output, the second adds a
  hook that does not change that and says what it does instead.
- **Interested in the framework question**: 0004 alone answers it, with
  figures.
- **Interested in observability**: 0005, which also documents the two
  aggregation traps of the unified trace.

## Writing a new one

`docs/adr/NNNN-titre-en-francais.md`, next free number, and the sections used
throughout this series: Context, Decision, Alternatives rejected,
Consequences. A "Consequences" section that lists only benefits has not been
written honestly; every ADR here names what its decision costs.

State what was **verified**, and how. A consequence that has not been
observed is written as a prediction, not as a result.
