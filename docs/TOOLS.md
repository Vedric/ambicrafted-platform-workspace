# Local diagnostics and operator tools

The control API, CLI and control MCP share one authenticated local service. They
operate on this workstation for one trusted operator. They do not create a tenant
boundary, upload client data, approve proposals or certify a production release.

## Readiness

Start the installed private console service, then run from the checkout:

```sh
./plateforme preparation
./plateforme doctor
```

Both commands call authenticated `GET /api/preparation`. Exit status is `0` when
every required check passes, `2` for an incomplete diagnostic, or the existing CLI
error status when the API cannot be reached. They print bounded JSON without keys,
tokens, paths to client files, runbook contents or raw dependency errors. The API
must be running; use `systemctl --user status ambicrafted-console.service` to
diagnose a stopped service.

The versioned response contains `schema_version`, UTC `checked_at`, `duration_ms`,
`scope: "local-private"`, `ready`, a `summary` of `pass`, `warn`, `fail`, `unknown`,
`checks`, `capabilities`, and `limits`. Each check contains an identifier, group,
status, required flag, label, message, bounded evidence and an optional suggested
command. Suggested commands are plain data. No check executes remediation.

Checks measure:

| Group | Evidence and limits |
| --- | --- |
| Runtime | Installed API package metadata, an executable agent entrypoint, console build entrypoint. Existence does not prove inference correctness. |
| Configuration | Current-owner private permissions on `.env` and state directory; configured agent destinations are loopback; development cross-origin access is disabled. Linux socket tables confirm that all observed listeners on the API port use loopback. No secret values or unrelated socket details are returned. |
| Services | HTTP health of the six fixed local service endpoints. This does not inspect arbitrary URLs or Docker environment values. |
| Routing | A live gateway model inventory using the confidential credential contains exactly `local` and `local-embed`. This does not inspect or certify the provider mapping behind an alias. |
| Knowledge | Count of readable validated local sources; existing vector collection is populated and green. Index freshness and relevance require separate qualification. |
| Voice | English and French offline runtime status with model-file validation. No microphone capture or audio playback occurs. |
| MCP | Actual stdio initialize and tool-list exchanges against the installed control and runbooks servers; exact expected inventories. No MCP tool is invoked by readiness. |

Independent probe groups run concurrently with a 20-second deadline per group.
Failures are isolated and reported as `unknown` without exception text. Concurrent
requests share a result cached for 30 seconds; service health and voice status also
have their existing 10- and 60-second caches. `checked_at` is the aggregate time,
not proof that every underlying component was sampled at that exact instant.

`ready` is **local operational readiness**, not release approval. Voice, telemetry
and a populated vector index are optional; core services, confidential routing,
source runbooks, installed runtimes and both MCP servers are required. Per-feature
capabilities describe measured prerequisites; they do not promise model quality.
Remote exposure, client acceptance, vulnerability remediation, restore drills,
capacity and recovery objectives remain independent release gates.

## Read-only MCP

The existing `.mcp.json` entry `plateforme-controle` starts the locked control
runtime over stdio. Its tools are:

| Tool | Parameters | Effect |
| --- | --- | --- |
| `plateforme_sante` | none | Read local service health. |
| `plateforme_preparation` | none | Read the readiness checklist. |
| `plateforme_outils` | none | Read the complete capability catalogue. |
| `plateforme_analyses` | none | Read the latest 25 analysis summaries. |
| `plateforme_analyse` | `identifiant`: 32 lowercase hex characters | Read one existing analysis and proposal. |
| `plateforme_runbooks` | none | List local runbooks. |
| `plateforme_lire_runbook` | `nom`: validated Markdown basename | Read one source with its digest. |
| `plateforme_recherche` | `requete`: 2–500 characters; `mode`: `texte` or `semantique` | Search exact text or use local embeddings and Qdrant. |
| `plateforme_journal` | `limite`: 1–100, default 20 | Read bounded audit metadata, without raw alert content. |

All tools advertise read-only, non-destructive, idempotent and closed-world MCP
annotations. The implementation only calls fixed authenticated GET routes on
loopback, rejects redirects, bounds JSON responses to 1 MB, applies an overall
40-second deadline and redacts errors. Search may use local compute and rate-limit
accounting; it does not modify the corpus or execute a remediation. There is no
arbitrary URL, shell command, file path, mutation, approval or operation tool.

The MCP process is a **trusted local client** and reads its credential from the
private environment file internally. A missing key or state directory is reported
as unavailable; MCP never initializes either one. Connect it only to a local confidential
model/client context: a remote consumer could upload the runbook or analysis
content it receives. The stdio server cannot enforce the consumer's later use of
that content. Read-only annotations are descriptive, not a substitute for the
restricted implementation and authenticated HTTP boundary.

## Voice language selection

```sh
./plateforme voix statut --langue en
./plateforme voix statut --langue fr
printf '%s' 'Ready for the next step.' | ./plateforme voix parler --langue en --sortie /tmp/operator-voice.wav
./plateforme voix transcrire --langue fr /path/to/private-capture.wav
```

The output path must be new; the CLI creates it with mode `0600`. Input recordings
must be private regular files. Text is read from stdin or a private file rather
than command arguments. Language defaults to `en`, accepts only `en` and `fr`, and
is forwarded to speech synthesis, transcription and assistant dialogue. HTTP
`GET /api/voix/statut?langue=fr` uses the same language contract as the optional
`langue` field of the three POST bodies.

## Verification

```sh
uv run --locked --project apps/control-api pytest apps/control-api/tests/test_preparation.py apps/control-api/tests/test_mcp_controle.py apps/control-api/tests/test_cli.py
```

The protocol tests run a real stdio MCP client and a real isolated HTTP API, with
synthetic state and no model inference. Unit tests separately verify health
degradation, routing inventory, private permissions, failure deadlines, cache
coalescing, language forwarding, invalid inputs and secret redaction. These tests
do not replace a live workstation readiness run or production qualification.

## Qualified workstation toolchain — 2026-09-27

The coordinated update pins Node 22.23.3 in `.node-version` and uses npm 11.10.0.
On this workstation the verified Node archive is installed privately under
`~/.local/share/ambicrafted/toolchains/node-v22.23.3-linux-x64/`; `node`, `npm` and
`npx` in `~/.local/bin` point to it. Select that directory through the existing
direnv setup or `export PATH="$HOME/.local/bin:$PATH"` before frontend/evaluation
commands. The system Node installation is unchanged. `node --version` should
report the pinned version. [Dependency maintenance](DEPENDENCY-UPDATES-2026-09-27.md)
records upstream checksums, action pins and the retained PostgreSQL major version.

No additional external-account connector is required for the implemented private
workflows. Configure only tools justified by the client mission and its approved
data boundary; the existing two MCP transports and nineteen readiness checks are
the supported starting point.
