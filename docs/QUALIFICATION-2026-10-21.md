# Candidate qualification — 21 October 2026

This assessment concerns console/API 0.5.0, SRE workflow 0.2.0 and speech 0.3.3.
The supported deployment remains a private Linux workstation for one trusted
operator, with loopback services, local confidential inference and explicit
human decisions. It is not commercial multi-tenant acceptance or a claim that
all vulnerabilities and reasoning errors have been eliminated.

This report attributes each result to its tested source and scope. Local checks,
hosted Actions, live promotion and independent human acceptance are separate
evidence. The recovery baseline for this delivery is
`6abed2a248c13c6120f8a5f2a792ff3b32c85d82`. The
[repository releases](https://github.com/Vedric/ambicrafted-platform-workspace/releases)
identify published versions; [delivery PR 70](https://github.com/Vedric/ambicrafted-platform-workspace/pull/70)
records the local deployment outcome separately. A source checkout alone does
not establish which version is in service.

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
1920 × 1080 MP4s of approximately 82–94 seconds, with four chapters each,
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
consistency review and the graph's human gate. An independent counter-test
also confirms that a source read as B and then A within one tool batch leaves
only A in the admissible registry; an intermediate B may therefore not count as
progress. Changing only the counter would not make B admissible evidence.
[ADR 0043](adr/0043-arret-recherche-sans-progres.md).

Legacy pending analyses keep their report and checkpoint. An incompatible
contract marker causes HTTP 409 before any decision mutation or queueing. A new
analysis needs a new identifier and the original observations from the operator;
the application cannot reconstruct the ephemeral original alert from extraction.

The local MCP gateway now uses cancellable POSIX input/output adapters through
the SDK's public transport interface. Real subprocess regressions reproduce and
correct hangs when a client keeps stdin open after initialization or stops
reading a large response. Backend cleanup stays in its owning task, including
startup failure; descriptor ownership and blocking modes are restored. The
supported transport remains Linux/WSL pipes or sockets, with a 1 MiB incoming
line ceiling and the existing smaller tool-argument limit. Regular-file
redirection is refused. [ADR 0045](adr/0045-arret-stdio-mcp-annulable.md).

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
The new six-case execution retained **4/6 mechanical contracts and 2/6 cases
in engineering AI review**. It took 189.884 seconds with 118,662 observed tokens;
source hashes and actual runtime identities remained stable. One case abstained
without a useful answer, one exhausted its observed token budget, one missed the
central sampling-bias explanation, and one invented prior approval of a rights
change despite the consistency review. The two retained answers have minor
limitations, including an incorrect kube-proxy/CNI example. The original human
review remains pending. This is evidence against an expert-autonomy claim, not
qualification by a renamed pass criterion.

The separate 63-case regression execution retained **36/63 mechanical contracts
and 28/63 cases in engineering AI review**, in 1,908.346 seconds with 1,210,687
observed tokens. Fifty-seven cases reached the human gate and six exhausted
their observed token budget. The source inputs and actual runtime identities
remained unchanged. The substantive review rejects incorrect PDB guarantees,
unsupported claims of irrecoverability, missed arithmetic and generic abstention
without useful case-specific questions. A gate reached is not a correct answer.
The original independent-human review remains pending; the AI review does not
replace it. These executions used frozen development source subsequently
committed in `669c7c5`, not a clean-clone execution of the final candidate.

## Image corrections and remaining findings

No finding is suppressed, no inventory is deleted to lower a count, and the
release image gate still fails on any CRITICAL/HIGH finding or incomplete scan.
The combined scan from clean commit `8f31ccbe` binds the eight corrected image
identities and reports **0 CRITICAL, 0 HIGH, 42 MEDIUM, 12 LOW and six UNKNOWN**
occurrences. Its database was updated on 20 October at 19:12 UTC. Downloading
the official database again on 21 October at 00:00 UTC returned exactly the
same database bytes. This database predates the CA disclosure below; the
separate trust-store tests establish that correction, not the scanner count.

The independent [hosted image workflow on `8f31ccbe`](https://github.com/Vedric/ambicrafted-platform-workspace/actions/runs/39517739747)
also completed **8/8 jobs successfully**, with the same severity totals. Its OCI
and root-filesystem identities differ from the local builds and are retained
separately; hosted results are not substituted for the exact local images used
for promotion. That run did not preserve the scanner database timestamp. The
follow-up workflow now retains database metadata and hashes alongside reports.

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

A later certifi CA-compromise disclosure required another correction after the
earlier scan. All seven Python locks now use official certifi 2026.10.19; the
API uses Pillow 13.0.0 for newly disclosed decoder flaws. All eight container
trust stores are separately corrected for the exact emSign ECC G3 root, including
Neo4j's default Java trust manager. Actual old/new root-set comparisons and
verification require G3 alone to disappear while unaffected roots still verify;
the application binaries and inventories remain intact.
[Trust-policy evidence and boundaries](../gateway/images/trust-policy/README.md).

The host uv tool was upgraded to 0.13.4 after official archive checksum and
GitHub artifact-attestation verification; CI uses that version too. The host's
system CA bundle still contains the affected root. Its update needs administrator
credentials unavailable to this session. This remains an explicit host security
action, with the verification and native Ubuntu correction procedure in
[HOST-TOOLS.md](HOST-TOOLS.md#host-certificate-trust-and-uv); container corrections
do not silently clear it.

## Verification evidence

Fresh clones of exact commit `8f31ccbe970a689c95ad479551b1927a32481f5d`
contained no private environment files or inherited virtual environments.
Locked installations and the workflow checks produced the following results:

| Check | Observed result |
| --- | --- |
| Python application suites | 1,156 passed: 259 SRE, 740 API, 48 runbooks, 109 speech |
| Branch coverage | SRE 88%, API 84%, runbooks 74%, speech 71% |
| Maintenance and evaluation contracts | 44 maintenance and 11 evaluation tests passed; the 18 scanner tests are already included in the maintenance count |
| Runtime Python dependency audits | Four projects and three locked scripts: no known findings at audit time |
| Console | 271 unit tests passed; production build, browser-test typing and npm advisory audit passed |
| Real offline speech | 25 tests passed on the native CPU path; nine selected regressions passed on a second AVX2 path |
| Lifecycle exercise | 25 cycles, 306 HTTP requests and three startups; SQLite integrity `ok`; no model calls |
| Build reproducibility on this host | Three independent locked installs produced the same 79 console build files byte for byte |

The Python suites ran in a network namespace with a negative connectivity
control. The 25 real-speech tests are intentionally skipped in the ordinary
speech suite and run separately with pinned, hash-verified model files. The
AVX2 subset overlaps those tests; it is not nine additional unique cases.
Dependency audits cover runtime dependencies according to the CI contract.
Build byte identity on one host is not a cross-platform reproducibility claim.

Clean candidate `56fa37712abfaecee7861a311f4114f4bf5f30b8` was prepared with
four new locked Python environments and a new npm install. Its production
source, locks, media, image inputs and maintenance scripts are identical to
`8f31ccbe`; the changes affect browser tests, scan-provenance reporting and
documentation. Its 271 console unit tests, build, browser-test typing, formatting
and npm audit passed again. All 79 built console files match the earlier build.

An independent artifact API review also exercised cancellation/retry, concurrent
deletion, changing quotas and stream setup failure. Those checks overlap the API
suite and must not be summed as independent coverage.

The initial complete browser execution on `8f31ccbe` passed 196 of 224 cases,
including all 34 WebKit cases. Its 28 failures were investigated: 25 exhausted
the real authentication ticket limiter because each short media case created a
new session, two expected a video error before requesting on-demand playback,
and one expected a deferred mobile diagram before scrolling it into view.
The follow-up tests share only one real authenticated session cookie in memory
per Guide worker, keep each browser context and local storage fresh, trigger an
actual failed video playback and observe a new request on retry, and scroll the
restored diagram into view before checking its layout. Authentication limits
and product behavior remain unchanged. The initial failures are retained.

The corrected full matrix on clean `56fa3771` then passed **226/226 cases**:
35 Firefox, 78 desktop Chromium, 78 mobile Chromium and 35 WebKit. There were
no retries, skips or flaky outcomes. The video retry now runs in all three
engines. The native projects took approximately 10.1 minutes and WebKit 3.7
minutes. The clone stayed clean and its build remained byte-identical to
`8f31ccbe`. WebKit used isolated Linux dependencies and software H.264 decoding;
the host loader cache was unchanged. These are browser-engine tests and mobile
emulation, not physical-device or Safari-product certification. Inference in
this browser suite is deliberately synthetic; real-model results are above.

Media validation checks twelve unique bilingual assets, narration decoding,
chapter durations and hashes. Browser tests exercise saved documents, geometry,
exports, reopening, memory drafts, injection refusal, print isolation, caption
persistence, transcripts, actual video progression and AAC decoding. Physical
speaker audibility, a particular microphone and a user's listening preference
remain outside those automated checks.

A separate HTTP/SQLite load exercise against clean commit `669c7c5` created
40 documents across five conversations, replayed all 40 operations without
duplicates, then served 640 authenticated exports using 16 concurrent workers.
Read/export p95 was 26.775 ms and maximum 40.115 ms on this workstation.
Unauthorized and cross-conversation reads were refused; deleting two
conversations made their 16 documents unavailable and left 24 valid documents
with SQLite integrity `ok`. Nine real rate-limit delays were respected; the
exercise took 547.244 seconds. Inference alone was deterministic synthetic
input. This is local storage/API evidence, not model latency, distributed load
capacity or a production SLO. Earlier harness mistakes are retained separately.

Hosted workflow and final browser results are linked from the release only
after completion. A previous run or a development virtual environment cannot
supply that evidence for a new commit. Component-level evidence can be reused
only when its source, locks and build inputs are verified unchanged; that is
not described as rerunning the earlier test on a later commit.

## Installed-instance acceptance and counterexamples

Commit `2a3664b3f506325682bd814c1e2b83473c3b0e55` was installed after a
quiesced backup, successful isolated restores with both candidate and recovery
runtimes, and verified copies of seven volumes. Original volumes, configuration,
environments and UI were retained. All eight running image IDs match the local
scan evidence. The previously existing rows and checkpoints remained unchanged.
Synthetic French and English speech was synthesized and transcribed correctly;
this does not validate physical speakers or a microphone.

The focused installed-instance browser journey exercised the legacy read-only
analysis, new-analysis form, Guide media/provenance, caption toggle, playback,
pause and responsive widths. These assertions passed with no JavaScript errors
or HTTP 5xx. The harness initially failed because its write guard counted two
blocked automatic model warm-up requests as business writes. That initial result
is retained. A separate read-only closure established preservation and session
revocation; it does not relabel the initial harness exit as a successful run.

Functional model acceptance **did not pass**. One synthetic contract-v3 analysis
reached its human pause with its own checkpoint in 34.87 seconds, using eight
calls and 26,008 reported tokens, but the result was an **abstention**. One diagram
request and one report request were not published after 22.21 and 24.25 seconds.
No partial conversation turn or artifact was saved. Four gateway calls returned
HTTP 200, but the installed code did not retain the precise failure category;
these outcomes cannot retrospectively be labelled safe semantic refusals.

A separate, explicitly instrumented diagnostic repeated each synthetic request
once without business persistence. The diagram passed schema validation but its
review rejected a worker-to-queue edge labelled "Consumes Jobs". The report was
accepted by the product, yet changed "no server logs captured" into logs being
"unavailable". That is a semantic overstatement the automatic review missed.
Neither a passing schema nor an all-retain review establishes factual correctness.
These diagnostic results do not establish the cause of the original failures.

The postpromotion backup `20261021T004643Z` restored successfully in isolation:
18 files, three analyses, two checkpoints, five conversations and 16 messages,
plus the service stores. The old pending analysis and checkpoint were preserved,
the source backup stayed unchanged, and no live database was restored. No new
artifact had been published, so actual artifact restoration and live document
exports were **not exercised** by this run. Database snapshots are individually
consistent, not an atomic whole-platform snapshot. The broader disposable API
and browser export tests remain separate evidence.

## Hosted CI and publication blocker

The [application CI on `8f31ccbe`](https://github.com/Vedric/ambicrafted-platform-workspace/actions/runs/39517724451)
completed seven jobs successfully; its console job was cancelled when the
follow-up commit was pushed. The overall run is **cancelled**, not successful.
The four Python installation logs confirm certifi 2026.10.19 and, for the API,
Pillow 13.0.0; their runtime dependency audits succeeded.

The [CI on `56fa3771`](https://github.com/Vedric/ambicrafted-platform-workspace/actions/runs/39520019662)
failed before any of its eight jobs executed a step. GitHub's annotation cites
failed recent account payments or a spending limit and directs the account owner
to **Billing & plans**. This is a hosting-account blocker, not an executed test
failure. It still means there is no successful hosted application CI for that
candidate. Local qualification is reported separately, never as a replacement
green GitHub status.

Application CI now runs on pull requests and pushes to `main`, with explicit
manual dispatch available before opening a PR. The release workflow invokes the
same jobs for a tag. This removes duplicate branch-push/PR runs and duplicate
standalone tag runs; it changes neither the jobs nor their acceptance criteria.
It does not resolve the account's billing restriction.

Private workstation deployment can be assessed from the exact local evidence and
recovery gates under the operator's authorization. The release workflow remains
unchanged: both application and image qualifications must succeed before it can
create a release draft. No manual release publication or gate bypass is justified
by the billing failure. Once the account is corrected, rerun qualification for
the exact intended tag, inspect its reports and review the generated draft before
publishing. [Delivery review and operational outcome](https://github.com/Vedric/ambicrafted-platform-workspace/pull/70).

The commits are locally verified SSH signatures, but GitHub reports an unknown
signing key for `56fa3771`. Registering the matching public key needs an account
authorization scope unavailable to this session. This is documented separately
from functional/security qualification in [host setup](HOST-TOOLS.md#commit-signing-and-github-identity).

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

The supported use remains a supervised personal workspace. The model-quality,
host-security and off-host recovery limits above prevent an unconditional
commercial-production sign-off.
