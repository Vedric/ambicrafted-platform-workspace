# Control-plane verification

This suite covers the private, single-operator control API in `apps/control-api`.
It does not certify model quality, browser accessibility, public multi-user deployment,
or the absence of all vulnerabilities. The SRE engine, offline speech runtime and
browser console have their own test suites.

## Reproduce

Run from the repository root:

```sh
uv sync --locked --all-extras --project apps/control-api
cd apps/control-api
uv run pytest tests -q --junitxml=/tmp/control-tests.xml
uv run coverage run -m pytest tests
uv run coverage report
```

`uv run --project apps/control-api pytest` alone does **not** change the working
directory. From the repository root, pass `apps/control-api/tests` explicitly or
change directory as above, to avoid collecting unrelated projects with a different
lockfile.

The fixtures create temporary private repositories and state directories. Ordinary
tests reject TCP connections and mock local HTTP dependencies. Transport tests
permit only their own ephemeral loopback listener in the client process; an isolated
Uvicorn subprocess serves synthetic data and its analysis consumer is disabled.
No test submits alerts to a real model, modifies the operator's `.env`, starts an
operational backup, or accesses the production SQLite state.

## Verification matrix

| Area | Evidence |
| --- | --- |
| Browser authentication | One-use tickets, concurrent redemption, hashed stored credentials, expiry, HttpOnly/SameSite cookies, logout and password-change revocation |
| HTTP boundaries | Host and Origin checks, CSRF, cross-site rejection, invalid/non-ASCII headers, strict boolean decisions, extra-field refusal, masked validation errors, bounded chunked requests |
| Analysis workflow | Real SQLite state transitions, metadata-only lists, pagination, exports, terminal SSE, cancellation, double-decision refusal, bounded queue and explicit operation allowlist |
| Confidentiality | Raw alert remains in memory and travels to the engine on stdin; output, errors, audit records and CLI ticket handling are checked for unintended disclosure |
| Filesystem | Private ownership/modes, path traversal, symbolic links, FIFOs, bounded UTF-8 reads, optimistic edits, concurrent edits and bounded revision history |
| Execution | Actual temporary subprocesses test stdin, progress events, exit-code/report agreement, malformed output, stdout/stderr bounds, cancellation and shutdown |
| Concurrency | Atomic human-decision transitions, first-start key initialization, cancellation/deletion during spawn, serial analysis execution and bounded conversation access to inference |
| Retention | Expired terminal and pending-human analyses/checkpoints, active/recent preservation, 30-day journal/revision policy and refusal to follow external paths |
| Local services | Cached health probes, malformed upstream schemas, bounded streaming JSON, strict local embeddings, asymmetric query prefix, absent confidential key and invalid vectors |
| Voice API | Authentication/CSRF, separate audio body limit, strict base64, decoded size, private temporary files, cleanup on failure/cancellation, concurrency refusal, fragmented subprocess JSON, output bounds and invalid/symbolic/FIFO audio output |
| Conversation | Allowed roles only, bounded history, final user turn, local alias and confidential credential, no tools or action authority, no persistent transcript and masked provider errors |
| MCP | Actual subprocess initialization and stdio calls through the authenticated HTTP API; exactly three read-only tools; an approval tool does not exist; multiple runbooks preserve separate MCP text content blocks |
| CLI | API parity, bounded private stdin/files, fixed loopback serving, secret-free browser opening, private exports, explicit deletion, systemd command construction and voice commands |

Regression tests exposed and accompanied fixes for non-ASCII authentication headers,
concurrent first-start key generation, malformed service responses, reflected
validation input, cancellation/deletion races, fragmented voice output and unsafe
voice output-file reads.

## Controlled load evidence

On the development workstation, a full run on 2026-09-26 passed 289 tests in 21.57
seconds, without warnings. Combined statement/branch coverage was 91% in that run: API 93%, authentication 96%, runbook editing 98%, state store 96%,
service probes 100%, voice bridge 95%, execution engine 87% and MCP adapter 89%.
Subprocess execution is also validated behaviorally and is not included automatically
in the parent process's coverage. These measurements describe
that working-tree run, not hosted CI or a released commit.

A real Uvicorn loopback run, with 16 concurrent clients, measured:

| Workload | Result |
| --- | --- |
| 48 creation requests | 0.248 seconds; exactly 12 accepted and 36 rejected because the queue was full |
| 160 authenticated list requests | 0.499 seconds; consistent results for every request |
| List-request latency, p95 | 57.4 milliseconds |

The queue consumer was deliberately suspended: these numbers measure HTTP,
authentication and SQLite behavior, **not** LLM throughput or voice latency.
They are a bounded local smoke/load experiment, not a sustained capacity benchmark.
The tests use broad 20-second deadlock guards rather than claiming the measured
latencies are portable service-level objectives. Each run records its own load
measurements as JUnit test-suite properties.

A release still requires checks on the final commit in a clean clone, browser
end-to-end tests and a real local model/speech exercise with synthetic inputs.
