# Security

The current security model is defined by
[ADR 0009](docs/adr/0009-garanties-verifiables-apres-audit.md).
It assumes a single trusted workstation user and a trusted local gateway.
It does not defend against root or a compromised model server.

The release image gate fails on any HIGH/CRITICAL occurrence or incomplete scan.
See the [24 October candidate qualification](docs/QUALIFICATION-2026-10-24.md) for the
candidate, exact scope and remaining upstream findings. Earlier dated assessments
remain historical. Functional qualification does not certify a vulnerability-free
deployment.

## Data classification and storage

| Data | Storage and routing |
|---|---|
| Raw alert supplied to the agent | In-memory invocation context and ephemeral local reasoning request; the added original-input message is not persisted |
| Extraction, injection quotations, model/tool messages and diagnoses | Confidential; local model only; graph checkpoints may retain identifiers missed by extraction |
| Checkpoints | SQLite file 0600; newly created parent 0700; existing parent permissions are not changed |
| Virtual/provider/master keys | Private `.env` files; never printed by provisioning or operational scripts |
| Backups | Local 0700 directory with private files; includes secrets, database contents and incident state |
| Saved conversations, extracted attachments and generated documents | Private console SQLite tables, local inference only; bounded retention and explicit deletion; generated content remains unverified |
| Runbooks | Versioned files; content remains untrusted input for reasoning |
| Traces | Local Tempo; tool arguments and raw HTTP/error bodies are not deliberately recorded by the agent |

Extraction is a model transformation, **not declassification**. All SRE model
stages, including consistency review, use `local` and `CONFIDENTIAL_KEY`.
Changing a reasoning
alias to an external alias is rejected before analysis. Gateway restrictions
and the absence of a fallback from `local` provide additional controls.

LangSmith's implicit tracing variables are disabled before orchestration
imports. A separately configured telemetry exporter or embedding gateway
must still be reviewed when its destination or implementation changes.

The daily retention timer removes inactive graph threads older than 14 days
and matching local backups older than 14 days. SQLite is vacuumed and its WAL
truncated after thread deletion. Daily scheduling adds up to a day to the
threshold, and an unavailable host delays execution. SSD/filesystem snapshots,
external backups and older copies created before hardening are outside this
logical deletion mechanism and need their own lifecycle.

## Enforced controls

- Unknown tools are refused. The model has no shell, write or arbitrary-HTTP
  tool. Diagnostic text is never executed by the platform.
- Every runbook read uses a bounded descriptor-based open, refuses symlinks
  and non-regular files, and validates the filename. Search is literal.
- Only complete read envelopes with a matching name and SHA-256 populate
  the provenance registry. An action must match a complete paragraph of the
  verified text, including any negation or prerequisite in that paragraph.
- Pending and rejected reports have no deliverable `diagnostic`. Approval
  previews show missing evidence and reported injections. Structured approval
  requires the actual boolean `true`, not a truthy string.
- Existing threads cannot be restarted as new incidents. Database operations
  are serialized by a lock; SQLite connections are closed by public helpers.
- Checkpoints from earlier delivery-contract versions cannot be approved;
  the API refuses incompatible decisions before mutation or queueing. The
  incident must be analysed again under a new identifier with its original input.
- Generated diagrams and reports use a bounded schema, plain text and code-owned
  rendering. Model HTML, SVG, links and scripts are rejected. A local review can
  reject a proposal but cannot certify it; memory writes require an explicit save.
- Tool, turn, context, alert-size, time and monetary limits are enforced at
  their respective boundaries. Resource cleanup can add time beyond a deadline.
- Unknown external costs, negative costs and non-finite numbers cause a
  stop. A post-call spending threshold is not an exact prepaid invoice cap.
- HTTP/MCP/configuration failures produce bounded, sanitized errors instead
  of copying upstream response bodies or validation inputs into reports.
- Uploaded documents require Linux namespaces, a read-only parser filesystem,
  native syscall restrictions and bounded streams. Missing isolation fails
  closed; see [the document boundary](docs/DOCUMENT-SECURITY.md).
- Encrypted backup exports require a verified inventory and the qualified age
  tool. Import stages into a new private directory and never activates restored
  services. Off-host custody remains a separate operator responsibility.

Offline regression tests cover these refusal paths. Real-service tests
add evidence about deployment and routing; they do not prove model quality.

## Limitations

Prompt delimiters and instructions reduce accidental instruction confusion;
they are not a proof that a model ignores every injection. A runbook can be
malicious or wrong, and a verified quote can still be irrelevant. Human
review, corpus review and scenario-based evaluations remain necessary.

The loop variant does not implement the graph's approval gate. It returns
an operator proposal. Do not wire either CLI's output to automatic shell
execution or treat `statut=complet` as authorization to change production.

Local binding reduces exposure but is not authentication against another
local process. PostgreSQL is not published; the other services bind their
published ports to loopback. Qdrant has no separate API key in this local
configuration. Container-to-container access remains possible on the stack
network. The model service listens on the configured Docker bridge address.

Pinned images still contain known upstream findings; see
[the dependency register](docs/DEPENDENCIES.md). There is no unqualified
claim that the platform is ready for sensitive multi-user production.

## Secrets and hooks

The private console adds mandatory authentication on loopback. CLI credentials
stay in the root private environment. Browser sessions use opaque HttpOnly,
SameSite=Strict cookies, CSRF tokens, an Origin allowlist and a Host allowlist.
Pending asynchronous document downloads are cancelled when the browser observes
session invalidation or logout, including HTTP200 session discovery returning
disconnected. They recheck cancellation before publishing a file; this is not
a fresh server authorization check and cannot retract an existing download.
Explicit logout first revokes the server session, signals cancellation and
clears private query state, then navigates within the existing document.
Tests replay the old cookie, revisit protected routes and release delayed
private responses after logout. A failed logout request reports an error and
does not claim successful revocation.
Cookies intentionally use local HTTP; exposing this server remotely requires
a separate TLS, identity and authorization design. One-use login links expire
after 60 seconds; sessions expire after 12 hours. Changing the password revokes
all sessions and outstanding tickets. Passwords are stored as salted scrypt hashes.

The control API caps request bodies, queue depth, subprocess outputs and execution
time. It runs one instance per state directory and one analysis at a time. Raw
alerts enter subprocesses on stdin, not command arguments. Console reports and
per-analysis checkpoints remain confidential; they are retained for 14 days after
their last activity, with active work excluded. The hourly maintenance loop also
expires audit events and editor revisions after 30 days. Backups have a separate
14-day policy and never contain active browser sessions or login tickets.

Microphone capture requires a browser gesture. Only local transcription receives
audio; audio is bounded and its private temporary directory is removed after the
operation. No browser cloud speech-recognition API is used. Saved conversation
history and extracted attachments persist in private SQLite storage and use the
restricted local gateway key. Selecting saved sources or copying a note to Neo4j
is explicit; no cross-client memory is inferred. AURA cannot approve analyses or
execute operations. The read-only control MCP
must only be launched by a trusted local operator; its credential grants API
authority even though its exposed tools do not mutate state.

Never display a secret or resolved environment configuration, including in
a diagnostic command. Provisioning writes virtual keys directly to `.env`.
Run only `docker compose config --quiet`; do not dump container environments.

The Claude `PreToolUse` hook denies recognizable literal secrets and malformed
hook input. Ordinary input returns a neutral result and does not override
normal permissions. It does not inspect command output or variable expansion.
Modern Claude hooks can replace some tool output before the model sees it,
but this cannot retract side effects or earlier telemetry copies; this
repository does not rely on that feature as an exfiltration boundary.
[Official hook reference](https://code.claude.com/docs/en/hooks#posttooluse-decision-control).

The Git pre-commit hook sends the staged diff to GitGuardian's API, as
explicitly documented in ADR 0008. Client data must never be staged here.
Its scan token is loaded from the private environment. Do not bypass a failed
hook with `--no-verify` or `SKIP`. Resolve a detected secret or restore the
scanner configuration; see [Contributing](CONTRIBUTING.md).

Report findings privately to the repository owner without including secret
values, customer logs or unredacted checkpoints.
