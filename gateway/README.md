# Gateway: LiteLLM + observability

The platform's Compose stack: LiteLLM (single entry point, aliases
`smart` / `balanced` / `fast` / `local` / `local-embed`, ADR 0001), its
PostgreSQL, Tempo (traces), Prometheus (metrics), Grafana, Qdrant (runbook
index, ADR 0002). It lives in this repository so that it can be rebuilt from
scratch (ADR 0006).

## Versioned / not versioned

Versioned, and enough to recreate the stack:

- `docker-compose.yml`: six services, every image pinned by digest
- `config.yaml`: LiteLLM aliases, fallbacks, callbacks. No secret in it
  (everything goes through `os.environ/...`)
- `observability/`: `tempo.yaml`, `prometheus.yml`,
  `grafana/datasources/datasources.yaml`
- `.env.example`: the list of expected variables, with fake values

Never versioned (secret or data):

- `.env`: ignored by `gateway/.gitignore` and by the root `.gitignore`.
  Check before any `git add`: `git check-ignore -v gateway/.env`
- the Docker volumes `gateway_pgdata`, `gateway_tempodata`,
  `gateway_promdata`, `gateway_grafanadata`, `gateway_qdrantdata`

## Rebuilding from scratch on a new machine

### Prerequisites

- Docker Engine with Compose v2 (`docker compose version`)
- Ollama on the host, reachable from the containers at
  `http://172.17.0.1:11434` (the Docker bridge address, not `localhost`),
  with the `coder` and `nomic-embed-text` models pulled (`ollama ls`).
  Without it, `local` and `local-embed` return errors; the frontier aliases
  still work.
- The subnet `172.28.0.0/24` free (`ip route`) — it is fixed in the Compose
  file.
- Ports `4000`, `4318`, `9090`, `3000`, `6333` free on `127.0.0.1`.

### 1. Variables

```sh
cd gateway
cp .env.example .env && chmod 600 .env
```

Then replace every value (all of the template's are fake):

| Variable | Role |
|---|---|
| `LITELLM_MASTER_KEY` | LiteLLM master key, `sk-` prefix |
| `POSTGRES_PASSWORD` | password of the LiteLLM database |
| `DATABASE_URL` | same password, host `postgres` (the service name) |
| `ANTHROPIC_API_KEY` | aliases `smart` / `balanced` / `fast` |
| `GRAFANA_ADMIN_PASSWORD` | Grafana's `admin` account |
| `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_SERVICE_NAME` | export of LiteLLM's traces to Tempo |

Check without starting anything:

```sh
docker compose config --quiet && echo OK
```

### 2. Start

One command is enough; Compose handles the ordering:

```sh
docker compose up -d
```

What happens, in order: `postgres` starts and must become `healthy`
(`pg_isready`) before `litellm` is launched; on first start LiteLLM creates
its schema in the database (a few tens of seconds,
`docker compose logs -f litellm`). `tempo`, `prometheus`, `grafana` and
`qdrant` start in parallel: Tempo writes its metrics into Prometheus by
remote write (retrying until Prometheus is ready), and Grafana provisions its
two data sources at startup.

The first launch pulls the images by digest: exactly what runs on the
original machine, not "the latest version".

### 3. Verify it works

In order — each step assumes the previous one:

```sh
docker compose ps                     # 6 services Up, postgres and qdrant (healthy)
curl -s localhost:4000/health/liveliness          # "I'm alive!"
curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" localhost:4000/v1/models
                                      # the 5 aliases, no provider model name
curl -s localhost:9090/-/ready        # Prometheus Server is Ready.
curl -s localhost:3000/api/health     # "database": "ok"
curl -s localhost:6333/healthz        # healthz check passed
```

Then an end-to-end call on the local alias (does not leave the machine):

```sh
curl -s localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" \
  -d '{"model":"local","messages":[{"role":"user","content":"ping"}],"max_tokens":5}'
```

Finally, in Grafana (`admin` / `GRAFANA_ADMIN_PASSWORD`), Explore → Tempo:
the `litellm-gateway` trace of the previous call must appear. That is the
proof that LiteLLM, Tempo and Grafana are talking to each other.

### 4. What the repository does NOT rebuild

These live in the volumes or outside the stack; they have to be recreated by
hand after starting from empty:

- **The LiteLLM virtual keys** (PostgreSQL database). At minimum
  `confidential-only`, restricted to `local` and `local-embed` (rule 2 of
  CLAUDE.md), and the broad key for orchestrated payloads. Through the UI
  (`http://localhost:4000/ui`) or:

  ```sh
  curl -s localhost:4000/key/generate \
    -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" \
    -d '{"key_alias":"confidential-only","models":["local","local-embed"]}'
  ```

  The resulting values go into the workspace `.env`
  (`CONFIDENTIAL_KEY`, `ORCHESTRATOR_KEY`), never into the repository.
  Verify the compartment with the negative test of ADR 0001: a call to
  `smart` with `confidential-only` must be refused.
- **The spend history** (same database): lost, not rebuildable.
- **The Qdrant runbook index**: `uv run --directory
  mcp-servers/runbooks indexer.py` recreates it from `runbooks/` (ADR 0002).
- **Past traces and metrics**: lost, they are operational data.
- **The Ollama models**: outside Compose, to be pulled on the host.

## Image pinning (rule 7)

Every image is pinned by the digest of **what was running**, read from the
live container, not from what the registry offers under a nearby name:

```sh
docker image inspect "$(docker inspect litellm --format '{{.Image}}')" --format '{{.RepoDigests}}'
```

The comment above each `image:` gives the version and the date of the
reading. To update: pull the new image, test it, then read its digest the
same way. Never go back to a tag (`main-stable`, `16-alpine`, `latest`):
they change content without changing name.

## What `docker compose config` does not prove

`docker compose config` is the minimal rebuildability test: it validates the
Compose syntax, the interpolation of the `.env` variables, and the existence
of the mounted files (`config.yaml`, `observability/*`). It does **not**
prove:

- that the images are pullable (the registry may have withdrawn a digest);
- that the services start: `config.yaml` can be syntactically correct and
  rejected by LiteLLM, a secret can be wrong;
- that the services talk to each other: service-name resolution, Tempo →
  Prometheus remote write, Grafana data sources, Ollama reachable from the
  container;
- that the volumes are recreated and filled correctly (LiteLLM schema
  created, healthy database);
- that the non-versioned data (virtual keys, Qdrant index) is in place.

Only the "Verify it works" section, run on a new machine, proves that. This
repository guarantees that you *can* go through it, not that it has been
gone through.

## Secret rotation

Changing a value in `.env` is not always enough: two services read their
variable only at the **first initialisation** of their volume and then keep
it in their own database. Procedure applied on 2026-08-27 (full rotation
after the values were exposed in an agent session, ADR 0007), in this order:

| Secret | Where it actually lives | How to change it |
|---|---|---|
| `LITELLM_MASTER_KEY` | `.env` only | replace, then `docker compose up -d` |
| `GRAFANA_ADMIN_PASSWORD` | Grafana database (volume `grafanadata`), read at first init only | replace in `.env` **and** apply it: `docker compose exec -T grafana grafana cli --homepath /usr/share/grafana admin reset-admin-password "$GRAFANA_ADMIN_PASSWORD"` |
| `POSTGRES_PASSWORD` | PostgreSQL catalogue (volume `pgdata`), read at first init only | 1) `ALTER USER litellm WITH PASSWORD '…';` passed **on stdin** to `docker compose exec -T postgres psql -U litellm -d litellm -q`; 2) replace `POSTGRES_PASSWORD` **and** the clear-text password inside `DATABASE_URL` (Compose does not interpolate a `${VAR}` inside a `.env` value); 3) `docker compose up -d` |
| `ANTHROPIC_API_KEY` | Anthropic console | revoke and recreate console-side, replace, `docker compose up -d` |

Method (lessons from ADR 0007: three Anthropic keys created and revoked
within an hour left a dead key in `.env`, and the diagnosis cost more than
the rotation):

- **one rotation at a time**, verified **end to end** before the next:
  `.env` updated, `docker compose up -d`, then a real call that exercises
  that secret (Anthropic key: a completion on `fast`; master key:
  `/v1/models`; Postgres: `/health/readiness` → `"db": "connected"`).
  Length and prefix prove the value changed, not that it is valid;
- revoke the old value **after** that success, never at the same time as
  creating the new one;
- on failure, a single retry, same protocol.

Traps encountered:

- `docker compose restart` does not re-read `env_file`. Only `up -d`
  recreates the container with the new environment.
- Testing the PostgreSQL password on loopback **inside** the container proves
  nothing: the official image's `pg_hba.conf` sets `127.0.0.1` to `trust`,
  so any password passes. Test from the Compose network (where the
  `scram-sha-256` rule applies):
  `docker compose run --rm --no-deps -T -e PGPASSWORD="$POSTGRES_PASSWORD" postgres psql -h postgres -U litellm -d litellm -c 'select 1'`.
  The final proof remains `litellm` recreated and `/health/readiness` →
  `"db": "connected"`.
- The virtual keys (`CONFIDENTIAL_KEY`, `ORCHESTRATOR_KEY` in the workspace
  `.env`) are hashed in the database: rotating the master key does not
  invalidate them. Check: `/v1/models` with each must still return 200.
- Consumers of the master key outside this directory: **none** (inventoried
  on 2026-08-27). The promptfoo harness (`evals/`) used an interactive
  `export OPENAI_API_KEY=…`; it now takes the `ORCHESTRATOR_KEY` virtual key
  through `apiKeyEnvar` (`evals/README.md`). A master-key rotation therefore
  has nothing to propagate; an `ORCHESTRATOR_KEY` rotation happens in the
  workspace `.env`.

Check a value without exposing it — length and prefix, never the value
(rule 8 of CLAUDE.md):

```sh
v=$(sed -nE 's/^LITELLM_MASTER_KEY=//p' .env); echo "len=${#v} prefix=${v:0:12}"
```

The transitional debt of the move (ADR 0006: the `~/platform/gateway`
symbolic link, containers to recreate) was settled on 2026-08-27 by that same
`up -d`; the link is gone.
