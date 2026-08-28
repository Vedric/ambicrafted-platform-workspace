# Operations

The runbook for the platform itself. Commands here were run on the machine
they describe; where something is stated from experience rather than from a
check you can reproduce right now, it says so.

Related: [`gateway/README.md`](../gateway/README.md) rebuilds the stack from
zero, [`ARCHITECTURE.md`](ARCHITECTURE.md) explains the topology,
[`SECURITY.md`](../SECURITY.md) covers the threat model.

## 🚦 Start, stop, status

```sh
cd ~/platform/workspace/gateway

docker compose up -d              # start; Compose orders postgres → litellm
docker compose ps                 # 6 services Up, postgres and qdrant healthy
docker compose logs -f litellm    # follow the gateway
docker compose stop               # stop, keep the containers
docker compose down               # remove the containers, KEEP the volumes
```

`docker compose down -v` destroys the volumes: virtual keys, spend history,
traces, metrics and the Qdrant index all go with them. There is no reason to
run it except to deliberately start from an empty stack.

**`restart` does not re-read `env_file`.** After changing `.env`, only
`up -d` recreates the container with the new environment. This is the single
most common way to spend twenty minutes on a secret that "did not take".

Ollama is not in Compose; it runs on the host.

```sh
ollama ps                         # what is currently loaded in VRAM
ollama ls                         # what is available
systemctl status ollama
```

## 🩺 Health

In order — each step assumes the previous one.

```sh
docker compose ps                                  # 6 Up
curl -s localhost:4000/health/liveliness           # "I'm alive!"
curl -s localhost:4000/health/readiness            # "db": "connected"
curl -s localhost:9090/-/ready                     # Prometheus Server is Ready.
curl -s localhost:3000/api/health                  # "database": "ok"
curl -s localhost:6333/healthz                     # healthz check passed
curl -s localhost:6333/collections/runbooks | jq '.result.points_count'
```

Aliases, without exposing a key value:

```sh
curl -s -H "Authorization: Bearer $ORCHESTRATOR_KEY" localhost:4000/v1/models \
  | jq -r '.data[].id'      # 5 aliases, and no provider model name
```

End-to-end on the local path — proves Ollama, the gateway and the routing at
once, and costs nothing:

```sh
curl -s localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $CONFIDENTIAL_KEY" -H "Content-Type: application/json" \
  -d '{"model":"local","messages":[{"role":"user","content":"ping"}],"max_tokens":5}'
```

And the agent's own offline proof, which needs none of the above:

```sh
cd agents/sre-agent && uv run --extra graphe pytest -q     # 49 passed
```

## 🔑 Secret rotation

Full procedure and the per-secret table are in
[`gateway/README.md`](../gateway/README.md). The method, which is what
actually costs time when it is skipped:

1. **One rotation at a time.** One secret, one new value, created once.
2. **Verified end to end before the next.** `.env` updated, `up -d`, then a
   real call that exercises *that* secret: Anthropic key → a completion on
   `fast`; master key → `/v1/models`; Postgres → `/health/readiness` showing
   `"db": "connected"`.
3. **Revoke the old value only after that success.** A few minutes of
   overlap cost far less than a dead key in `.env`.
4. On failure, **one** retry, same protocol. No burst of keys in the console.

Check a value without displaying it (rule 8):

```sh
v=$(sed -nE 's/^LITELLM_MASTER_KEY=//p' .env); echo "len=${#v} prefix=${v:0:12}"
```

That proves the value **changed**. It does not prove it is **valid** — only
an end-to-end call does. ADR 0007 exists because that distinction was learned
the expensive way: a correctly-shaped but already-revoked key sat in `.env`
while the investigation went looking at the gateway.

## 🧹 Checkpoint purge

Graph checkpoints contain the `Extraction`, i.e. data derived from a client
alert, and they survive the process. They are retained for 14 days by
default — the same window as Tempo's trace retention (336 h), so a thread and
its trace expire together.

```sh
cd agents/sre-agent
uv run --extra graphe sre-agent-graph --purger --simulation   # list, delete nothing
uv run --extra graphe sre-agent-graph --purger                # default 14 days
uv run --extra graphe sre-agent-graph --purger --avant 7
uv run --extra graphe sre-agent-graph --purger --json | jq .
```

Nothing triggers this automatically. It is a manual step or a cron entry.

A thread paused on the human gate ages like any other and is purged like any
other; the report flags it (`en_pause`) so the operator can see it. An
approval that has not come in two weeks is not coming — the alert was handled
another way.

The purge runs `VACUUM` and truncates the WAL afterwards. That is not
tidiness: deleting rows leaves the freed pages inside the file and a copy in
the write-ahead log, so alert-derived data would otherwise survive its own
purge.

Inspect a single thread without executing anything:

```sh
uv run --extra graphe sre-agent-graph --etat --thread-id sre-abc123def456
```

## 🔎 RAG reindexing

The index is **not** refreshed automatically. Run this after any change under
`runbooks/`:

```sh
uv run --directory mcp-servers/runbooks indexer.py --dry-run   # split only, no network
uv run --directory mcp-servers/runbooks indexer.py             # embed and write
```

`--dry-run` is the right first move: it shows the section split and the
heading path of every fragment without calling the gateway or Qdrant. If a
runbook is chunked in a way that would return half a procedure, you see it
there.

The run is idempotent: the collection is recreated and point ids are
deterministic (UUIDv5), so reindexing never duplicates and never leaves an
orphan fragment behind from a renamed section.

Requires `CONFIDENTIAL_KEY` in the environment — the embeddings go through
the gateway on `local-embed`, with the restricted key, never straight to
Ollama.

Current state, for comparison after a change:

```sh
curl -s localhost:6333/collections/runbooks \
  | jq '{points: .result.points_count, dim: .result.config.params.vectors}'
# → 7 points, size 768, Cosine
```

## 💸 Reading spend

The UI is at `http://localhost:4000/ui`. For the API, note that
`LITELLM_MASTER_KEY` lives in `gateway/.env`, which direnv does **not** load —
the root `.envrc` only loads the root `.env`. Load it without printing it:

```sh
cd ~/platform/workspace/gateway && set -a && . ./.env && set +a
curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" localhost:4000/spend/logs | jq length
```

Three things about this endpoint that are easy to get wrong, all verified on
this instance:

- **It is sorted newest-first**, not chronologically. `.[0]` is the most
  recent call and `.[-1]` the oldest. A `tail` gives you the beginning of
  history, not the end.
- **It returns everything** — 226 rows here, with no default limit. Filter
  client-side or use the date parameters.
- **The `model` field mixes aliases and resolved provider names.** The same
  traffic appears as `balanced` on some rows and
  `anthropic/claude-sonnet-5` or `claude-sonnet-5` on others, depending on
  the call path. A naive `group by model` therefore splits one alias across
  several buckets and understates it. This is the spend-side twin of the
  `gen_ai.request.model` ambiguity documented in ADR 0005.

The `api_key` column is a 64-character SHA-256 hash, never a key value
(verified by shape, not by reading it).

## 🔭 Reading traces

Grafana → Explore → Tempo data source. One alert is one trace, rooted at
`task.incident_analysis`.

```traceql
{ resource.service.name = "sre-agent" }
{ resource.service.name = "sre-agent" && name = "task.incident_analysis" }
{ span.ambicrafted.outcome = "budget_exhausted" }
{ span.ambicrafted.data_classification = "confidentiel" }
{ trace:id = "2e29b87679545d131e5d567d4c448b39" }
```

**The prefix is mandatory and it is the most common TraceQL mistake here.**
`service.name` alone matches nothing; it must be `resource.service.name`.
Span attributes need `span.`, resource attributes need `resource.`, and
trace-level fields use the `trace:` namespace. An unprefixed attribute is not
an error — it silently matches nothing, which reads exactly like "no data".

**Never aggregate `gen_ai.*` or `ambicrafted.cost_usd` without a service
filter.** Since ADR 0005 unified the traces, four `gen_ai.usage.*` keys are
emitted identically by the agent and by the gateway, so a sum over a trace
counts every call twice — wrong by a factor of exactly 2:

```traceql
{ trace:id = "…" && resource.service.name = "sre-agent" && span.gen_ai.usage.input_tokens > 0 }
  | sum(span.gen_ai.usage.input_tokens) > 0
```

To see which provider model an alias resolved to — rule 1 made verifiable
from the trace, since the code only ever knows the alias:

```traceql
{ resource.service.name = "sre-agent" && span.gen_ai.request.model = "smart" }
  >> { resource.service.name = "litellm-gateway" && name = "litellm_request" }
  | select(span.gen_ai.request.model, span.gen_ai.response.model)
```

An alert trace is now 70–80% gateway spans. Collapsing the
`Received Proxy Server Request` nodes gives back the agent-only view;
expanding them shows, per call, the time spent in authentication, routing and
at the provider.

## 🧯 Troubleshooting

### Traces are not arriving in Tempo

**The trap first: the absence of an error proves nothing.** Tracing is
designed never to fail the agent — if the collector is unreachable, the
export fails inside a background thread and the analysis continues normally.
A perfectly successful run with a printed trace id is entirely compatible
with nothing having been stored. **The only valid test is to go and find the
trace.**

This is not hypothetical. `config.py` shipped a default OTLP endpoint of
`http://172.28.0.3:4318` — a container address. Container addresses are
handed out in start order and change at the first `up` that recreates a
container; `172.28.0.3` had since become **Grafana**, while Tempo had moved
to `.4`. The agent had been exporting into a closed port, silently, with no
symptom anywhere. Fixed: the default is now `http://127.0.0.1:4318`, which
Compose publishes and which does not move.

Diagnose, in this order:

```sh
# 1. Where is the agent actually exporting?
cd agents/sre-agent && uv run python -c \
  "from sre_agent import config; print(config.OTLP_ENDPOINT, config.TRACAGE_ACTIF)"

# 2. Is that endpoint alive? 405 is the RIGHT answer (GET on a POST route).
#    000 means the connection failed — that is the symptom.
curl -s -o /dev/null -w '%{http_code}\n' --max-time 4 http://127.0.0.1:4318/v1/traces

# 3. Is Tempo publishing the port at all?
docker compose ps tempo    # expect 127.0.0.1:4318->4318/tcp

# 4. The real test: run something, take the trace id, and go and find it.
#    Tempo's API is on 3200, which is NOT published; query it from a
#    container that is on the Compose network and has curl.
docker compose exec -T grafana \
  curl -s -o /dev/null -w '%{http_code}\n' "http://tempo:3200/api/traces/<TRACE_ID>"
# 200 = stored. 404 = it never arrived.
```

A healthy run currently gives 52 spans for the hand-written loop: 10 from
`sre-agent` and 42 from `litellm-gateway`, one root, and the five gateway
server spans attached under their `llm.*` parents.

If tracing is deliberately off, `SRE_TRACAGE=0` — that is also what the test
suite sets, in `conftest.py`, so that an absent collector does not turn a
test failure into a timeout.

### Docker will not start after editing `/etc/docker/daemon.json`

`dockerd` refuses to start on a malformed or conflicting `daemon.json` and
the failure surfaces as a systemd start failure, not as a JSON error where
you would look for it. `default-address-pools` is the usual culprit: a pool
that overlaps a network already in use, or a syntax slip, and the daemon will
not come up at all.

```sh
sudo dockerd --validate --config-file /etc/docker/daemon.json   # syntax check
journalctl -u docker -n 50 --no-pager                           # the real reason
ip route                                                        # what is already taken
```

The current `daemon.json` on this machine sets only `runtimes` and
`log-opts`; it does **not** define `default-address-pools`. The stack takes
the other route instead: the Compose file fixes its own subnet to
`172.28.0.0/24`, chosen outside the ranges already in use and verified with
`ip route` (ADR 0001). That keeps the address decision inside the repository
rather than in a global daemon file.

### A systemd service is in a crash loop

**Always `systemctl reset-failed <service>` first, before any diagnosis.**

`Start request repeated too quickly` is not a cause. It only says that
systemd gave up on restarting, and while that state persists it masks the
real error — you will read the same misleading line no matter what you fix.

```sh
sudo systemctl reset-failed <service>      # FIRST, always
journalctl -u <service> -n 100 --no-pager | grep -iE 'error|fatal|denied'
systemctl cat <service>                    # including drop-in overrides
```

Frequent causes: a path the service user cannot reach, an environment
variable pointing at something absent, a bind to an address that does not
exist yet. Fix through `systemctl edit`, never the shipped unit file, then
`daemon-reload`, `reset-failed`, `restart`, and check it is actually
listening with `ss -tlnp`.

This is also the subject of `runbooks/service-systemd-crash-loop.md`, which
is what the agent finds when it is asked about it.

### Ollama crash-loops with `permission denied`

Do **not** redefine `OLLAMA_MODELS` to a path under the home directory. The
service runs as the `ollama` user, which cannot traverse `/home/<user>`; the
result is a permanent crash loop, and the message points at the model
directory rather than at the permission.

Leave the model store where the package put it. On this machine the service
sets `OLLAMA_HOST=172.17.0.1:11434` — the Docker bridge address, so that
containers can reach it — plus keep-alive and cache tuning, and deliberately
does **not** set `OLLAMA_MODELS`.

From inside a container, Ollama is `http://172.17.0.1:11434`. Never
`localhost`: inside a container that means the container.

### The gateway answers 401 or 403

- **401** — the key is not recognised. Check length and prefix (never the
  value). Remember that virtual keys are hashed in Postgres, so rotating the
  master key does **not** invalidate them.
- **403 `key not allowed to access model`** — this is usually the
  compartment working as designed: `confidential-only` is restricted to
  `local` and `local-embed`, so a frontier alias is refused. If you see this
  from the agent, something upstream chose the wrong alias for a confidential
  payload, and barrier 1 should have caught it first. That is a bug worth a
  test, not a configuration to relax.
- **Authentication error on `fast` only** — the Anthropic key. Length and
  prefix will look right even if the key was revoked provider-side. Compare
  against the provider console.

### `semantic_search` returns a message instead of results

By design it never raises; it degrades and names the cause. Read what it
says:

| Message mentions | Do this |
|---|---|
| missing dependency | `cd mcp-servers/runbooks && uv sync` |
| collection absent | `uv run --directory mcp-servers/runbooks indexer.py` |
| Qdrant unreachable | `cd gateway && docker compose up -d qdrant` |
| embedding failed | check `CONFIDENTIAL_KEY` is loaded, and the `local-embed` alias |

In every case `search_runbooks` still works — it depends only on the file
system. That is the whole point of degrading rather than raising.

### The indexer reports an unexpected dimension

`Dimension inattendue : N au lieu de 768` means the `local-embed` alias no
longer resolves to `nomic-embed-text`. Fix the alias in
`gateway/config.yaml`; do not adjust `DIMENSION` to match, or search quality
will drop silently.

## ⚠️ Hollow checks

Checks that look like verification and prove nothing. Each of these has cost
time on this platform.

| The check | What it actually proves | What it does not |
|---|---|---|
| `docker compose config --quiet` | syntax, variable interpolation, presence of mounted files | that images are pullable, that services start, that they talk to each other, that volumes recreate |
| Length and prefix of a secret | the value **changed** | that it is **valid** — only an end-to-end call proves that |
| `psql` on loopback **inside** the Postgres container | nothing about the password | the official image's `pg_hba.conf` sets `127.0.0.1` to `trust`; any password passes. Test from the Compose network, where `scram-sha-256` applies |
| The agent ran with no error and printed a trace id | the agent worked | that the trace was stored — tracing fails silently by design. Go and fetch the trace |
| `docker compose restart` after editing `.env` | the container restarted | that it read the new environment — only `up -d` recreates it |
| A `gen_ai.usage.*` sum over a trace | nothing usable | it double-counts without a `resource.service.name` filter |
| A TraceQL query returning nothing | nothing | an unprefixed attribute matches nothing silently; check `span.` / `resource.` first |
| The `block-secrets.sh` hook is installed | literal secrets in a command or a write are refused | that a secret cannot leak — it never sees command **output**, which is how the ADR 0007 incident actually happened |
| Grafana shows a `litellm-gateway` trace | the gateway is exporting | that the **agent** is exporting; before ADR 0005 those were two disconnected trees |

The pattern is the same every time: **the check observes the thing that is
easy to observe, next to the thing you care about.** When a control matters,
verify it by its effect — a refusal that actually happened, a trace you
actually retrieved, a call that actually returned 200.
