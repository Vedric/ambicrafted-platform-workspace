# Candidate qualification — 21 October 2026

This assessment concerns console/API 0.5.0, SRE workflow 0.2.0 and speech 0.3.3.
The supported deployment remains a private Linux workstation for one trusted
operator, with loopback services, local confidential inference and explicit
human decisions. It is not commercial multi-tenant acceptance or a claim that
all vulnerabilities and reasoning errors have been eliminated.

**Qualification is in progress.** The development results below are evidence of
specific checks, not fresh-clone CI, hosted Actions, completed live promotion or
independent human acceptance. The previous deployed baseline is
`6abed2a248c13c6120f8a5f2a792ff3b32c85d82`. It remains in service until the new
candidate passes the separate promotion and recovery gates.

## Delivered behavior

AURA can propose a saved diagram or structured report from a conversation and
its selected local attachments. The operator can select the response format or
request it explicitly. A bounded generation and a separate bounded consistency
review must both complete before a document is published. A refusal publishes
no partial document; a repeated operation returns the saved result without
creating duplicates. Neither model call can write memory or execute actions.

Diagrams are laid out by the locally hosted ELK worker, with measured multiline
labels, groups, routed connections, legends and visible source markers. The
workspace supports actual size, zoom, fit, expanded view and horizontal/vertical
layout. SVG/PNG exports include the full legend and source catalogue. JSON and
Markdown exports use authenticated, conversation-scoped API routes; the CLI can
export the same saved document. Printing produces a paginated text report or
complete diagram outline, rather than shrinking a large graph until unreadable.
References identify supplied context, not independently verified facts. The
complete JSON retains source hashes; a generated SVG is not a signed evidence
bundle. [Artifact contract and limits](AURA-ARTIFACTS.md).

A document can prepare an editable memory note. Its default type is a question;
the operator must review it, choose the scope and explicitly save. Conversation
history is available to later turns in that conversation, within the existing
limits. This is not autonomous learning or cross-client memory sharing.

The User guide now contains six workflows in each language: twelve native
1920 × 1080 MP4s of approximately 83–95 seconds, with four chapters each,
optional captions, complete transcripts and practical examples. These record
the real disposable UI with deterministic synthetic responses; they are not
proof of real-model accuracy or physical microphone/speaker operation. The
workflows cover first steps, voice, supervised investigation, documents/memory,
backup/recovery and monitoring. [Playback, provenance and rebuild](GUIDES.md).

## Agent behavior and quality limits

The SRE loop and graph retain verified source reads, bounded tools and budgets.
A separate local consistency review checks the proposed reasoning, source
coverage and selected calculations. Arithmetic itself uses deterministic decimal,
date and unit handling, but the model chooses which operands and propositions
to inspect. Correct arithmetic on the wrong operands is still a wrong review.
A successful review can retain a proposal, never certify its correctness or
replace a human decision. [ADR 0041](adr/0041-revue-coherence-agent-bornee.md).

After two consecutive tool rounds with no new verified source name/content hash,
the workflow makes at most one structured finalisation call without tools. The
existing token, turn, time and cost ceilings still apply. No verified read means
no forced conclusion. This may stop a useful search early; it proves neither
source sufficiency nor relevance. Finalisation still passes source checks,
consistency review and the graph's human gate.
[ADR 0043](adr/0043-arret-recherche-sans-progres.md).

Legacy pending analyses keep their report and checkpoint. An incompatible
contract marker causes HTTP 409 before any decision mutation or queueing. A new
analysis needs a new identifier and the original observations from the operator;
the application cannot reconstruct the ephemeral original alert from extraction.

The first twelve newly prepared model cases retained only **5/12 mechanical
contracts and 5/12 cases in engineering AI review**. Three exhausted their
budgets after repeated searches. Other failures included irrelevant arithmetic,
incomplete conclusions and abstention on answerable questions. These failures
remain evidence, not successes renamed as safe behaviour. Enabling model
reasoning in a separate trial exhausted its 2,500-token review allocation on the
first case without a valid result; that change was not retained.

All 63 previously inspected cases are now regressions. Six new holdouts were
prepared before the next frozen-source execution, with their input hash and
history retained in the [qualification suite](../evals/qualification/README.md).
The new run must report usefulness, factual errors, abstention, tokens and latency
separately. An engineering AI review is not independent human acceptance.

## Image corrections and remaining findings

No finding is suppressed, no inventory is deleted to lower a count, and the
release image gate still fails on any CRITICAL/HIGH finding or incomplete scan.
The fresh combined eight-image scan must bind the final source and actual image
identities; a successful individual scan is not that combined acceptance.

| Corrected derivative | Individual scan: Critical / High / Medium / Low / Unknown | Qualification |
|---|---|---|
| Grafana 13.2.4, r4 | 0 / 0 / 0 / 0 / 1 | Rebuilt core and required plugin backends; positive and negative signature checks; real Prometheus/Tempo queries and dashboard rendering |
| Qdrant 1.19.2, r4 | 0 / 0 / 23 / 11 / 0 | Real redirect credential-leak regressions, 167 UI tests, migration, persistence, snapshots, rollback and dashboard navigation |
| Tempo 3.0.3, r3 | 0 / 0 / 0 / 0 / 1 | Corrected exporters and authenticated timezone package; ingestion/query and package-content verification |

These counts are package occurrences at the recorded scan time, not proven
exploitation paths. The Qdrant r3 scan first appeared clean at HIGH severity, but
a later fresh database found two `follow-redirects` advisories. The final r4
really uses 1.16.1, and both credential leaks are reproduced against 1.16.0 before
the fixed tests pass. Initial failed experiments and the superseded scan remain
in private qualification evidence. [Qdrant build and residual review](../gateway/images/qdrant/README.md).

Grafana's private distribution retains the original verifier for official
signatures. Its narrow additional trust path accepts only the pinned local
public key, two exact plugin identifiers/versions and exact signed manifests,
then performs the ordinary file, path, version and root-URL checks. There is no
blanket unsigned-plugin allowance. Eleven unused bundled plugins are removed;
the required Prometheus and Tempo frontends remain from their official releases.
The signing key is private and absent from source/build inputs. The distribution
is qualified only for `http://localhost:3000/` and `http://127.0.0.1:3000/`.
[ADR 0042](adr/0042-distribution-grafana-privee-corrigee.md).

Two dependencies still carry UNKNOWN advisories for unused legacy OpenPGP code.
The Grafana build verifies that it is absent from the compiled package closure;
this is applicability evidence, not deletion of the advisory. Qdrant's remaining
MEDIUM/LOW findings are visible, including three reviewed Rust LOW findings with
no applicable trigger established in the inspected use. This does not prove
that no trigger or unknown vulnerability exists.

## Verification recorded so far

Development validation includes 259 SRE tests, 697 API tests before the final
search-stopping addition and 67 API checks after it, plus typing/lint/packaging.
An independent artifact API review ran 196 existing tests and four counterexamples
for cancellation/retry, concurrent deletion, changing quotas and stream setup
failure without establishing a new defect. These overlap the API suite and must
not be summed as independent coverage.

Media validation checks twelve unique bilingual assets, narration decoding,
chapter durations and hashes. Browser tests exercise saved documents, geometry,
exports, reopening, memory drafts, injection refusal, print isolation, caption
persistence, transcripts, actual video progression and AAC decoding. Physical
speaker audibility, a particular microphone and a user's listening preference
remain outside those automated checks.

Fresh-clone checks, hosted CI, combined image scanning, full browser results,
new model qualification and live promotion/recovery are recorded only after
they finish. A previous run or a development virtual environment cannot supply
that evidence for a new commit.

## Conditions for use and release

- Keep the private single-operator boundary, local confidential model route and
  explicit approval. Remote multi-user exposure needs a separate security design.
- Review generated claims and original evidence. Current automated model review
  does not justify autonomous incident decisions or a claim of expert reliability.
- Complete a fresh backup and isolated restore against the exact deployed data
  and images before promotion, preserving the legacy pending analysis and its
  checkpoint. Rollback retains candidate writes for later reconciliation.
- Maintain an encrypted off-host backup and separately held recovery identity;
  a local restore does not establish off-host custody or disaster recovery.
- Re-scan exact images and dependencies before publication and after updates.
  A zero HIGH/CRITICAL result does not imply zero vulnerabilities or pentest immunity.

The current evidence supports continuing a supervised personal workspace
qualification. It does not yet justify a stable commercial-production sign-off.
