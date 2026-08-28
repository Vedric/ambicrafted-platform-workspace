# ADR 0006: the gateway stack lives in the repository

Status: accepted
Date: 2026-08-25

## Context

The gateway (LiteLLM, PostgreSQL, Tempo, Prometheus, Grafana, Qdrant) existed
only on disk, in `~/platform/gateway/`, outside any repository. The founding
principle of the platform is to be rebuildable from the repository; without
the stack, that principle was not held: a lost disk took away the most
critical layer.

Preliminary inspection of the cross-references from the workspace to
`~/platform/gateway`: five files (`CLAUDE.md`,
`mcp-servers/runbooks/{server,indexer}.py`, `sre_agent/config.py`,
`.claude/settings.json`), **all of them human-readable strings** (docs, error
messages, docstring, read-refusal rule). No functional dependency on the
path. The only real coupling is on the Docker side: the containers carry
`com.docker.compose.project=gateway` and the absolute path of the mounts; the
volumes are named `gateway_*`, the prefix coming from the base name of the
directory.

## Options

1. **Move** `gateway/` into the workspace.
2. **Leave in place and link**: a symbolic link
   `workspace/gateway → ~/platform/gateway`. Git commits a symbolic link as a
   link: a clean clone has no content at all. Does not meet the objective.
3. **Move and keep a link** at the old location, permanently. Two paths for
   the same Compose file. Compose computes a configuration hash per service
   that includes the absolute paths of the bind mounts; a `docker compose up`
   launched sometimes from one path, sometimes from the other, would recreate
   the containers on every alternation. A permanent trap with no upside,
   since nothing depends on the path.
4. **Separate repository** for the stack. Possible, but contradicts "the
   workspace is the platform's repository" and doubles maintenance (two
   repositories to clone in order to rebuild).

## Decision

Option 1: `~/platform/gateway` becomes `~/platform/workspace/gateway`, the
five references are updated, no permanent link.

With, in the same pass:

- `name: gateway` at the top of the Compose file. Without it, the project
  name, and therefore the volume prefix, depends on the directory name: a
  clone into a differently named directory would create a second, empty stack
  colliding on ports with the first. That is the opposite of the desired
  reproducibility.
- Digest pinning of the three images that were not pinned
  (`litellm:main-stable`, `postgres:16-alpine`, `qdrant:v1.19.0`), recorded on
  the running containers, not on the registry (rule 7). The `main-stable` tag
  pointed that day to the same digest as the one in service; that is a
  calendar coincidence, not a guarantee.
- `.env.example` with explicitly fake values; `.env` stays ignored, verified
  by `git check-ignore` before any `git add`. The `.env.*` rule of the root
  `.gitignore` would have ignored `.env.example`: exception `!.env.example`
  added.
- `gateway/README.md`: rebuilding from scratch, verifications, and the
  explicit list of what `docker compose config` does not prove.

## Consequences

- A clone of the repository plus a `.env` is enough for `docker compose up -d`
  on a fresh machine. What the repository does not rebuild (virtual keys,
  spend, Qdrant index, traces) is listed in the README with the recreation
  procedure.
- **Recreation debt.** The move was done without stopping the services. The
  running containers still carried the old mount paths: on the next
  `docker compose up -d` from the new directory, Compose would recreate them
  (a few seconds of interruption, volumes preserved thanks to
  `name: gateway`). In the meantime, a **transitional** symbolic link
  `~/platform/gateway → workspace/gateway` protected automatic restarts
  (`restart: unless-stopped`, mounts declared as absolute `Binds`: without the
  link, Docker would create a directory in place of the file and the
  container would not come back up). The link was to be deleted right after
  that first `up`, so as not to fall back into option 3.
  **Settled on 2026-08-27**: `up -d` from `workspace/gateway`, six containers
  recreated on the new mount paths, link deleted.
- The proof of rebuildability provided at that date is `docker compose config`
  on a clean clone with a `.env` built from `.env.example`. It proves the
  syntax, the interpolation and the presence of the files; neither the
  startup, nor the communication between services, nor the recreation of the
  volumes. A full run-through on a fresh machine remains to be done.
