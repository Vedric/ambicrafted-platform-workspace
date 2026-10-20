# 0039 — Explicit volume selection for local recovery

Status: accepted, 2026-10-20.

Upgrades can migrate persistent data. Reverting an image does not reverse that
migration. A private Compose override also fails to cover the memory installer's
explicit `-f neo4j-memory.yml` invocation.

The seven volumes therefore accept optional private environment variables for
their physical names. Defaults use `${COMPOSE_PROJECT_NAME}` and preserve the
existing project-scoped names, including custom project names. The five core
selectors live in `gateway/.env`; the two memory selectors live in root `.env`,
which the memory installer already loads. Existing service commands and mount
targets are unchanged.

The operator can copy stopped volumes to reviewed new names, select them, and
retain the old volumes for rollback. Selection does not copy or validate data:
Compose can create an empty volume if a selected name is absent. The deployment
procedure must verify inventory, ownership, backups and restoration before start.
No automatic migration, deletion, failover or security-gate exception is added.

Validation renders both Compose files using only synthetic variables, without a
Docker daemon: original defaults, custom environment project, CLI project
precedence, empty variables, explicit names and partial overrides.
