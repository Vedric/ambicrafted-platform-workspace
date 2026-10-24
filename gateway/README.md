# Gateway stack

Six core services: LiteLLM, PostgreSQL, Tempo, Prometheus, Grafana and Qdrant.
The optional `observability` profile adds the platform metrics exporter;
`neo4j-memory.yml` defines dedicated memory separately. The candidate uses eight
local security derivatives with pinned upstream inputs. Ollama remains on the
host. See the image-specific build records and
[the dependency register](../docs/DEPENDENCIES.md).

The Compose files declare the candidate versions; they do not establish which
images a running installation currently uses. The
[20 October qualification](../docs/QUALIFICATION-2026-10-20.md) records outstanding
image findings and the blocked release gate. Back up and qualify an upgrade
before replacing existing services.

## Initial setup

```sh
cd gateway
cp .env.example .env
chmod 600 .env
$EDITOR .env
cd ..
# Requires apache2-utils (htpasswd); generates secrets without displaying them.
uv run --locked scripts/securiser_services.py
cd gateway
docker compose config --quiet
docker compose up -d --build --wait --wait-timeout 180
cd ..
uv run --locked scripts/plateforme.py creer-cles
```

Replace template instructions locally without displaying the generated values.
The PostgreSQL password in `DATABASE_URL` must match `POSTGRES_PASSWORD`.
Use a URL-safe generated value or percent-encode it. The external-provider key
is for separate public/synthetic use; the SRE agent uses only its restricted
local virtual key. Do not print `/key/generate` responses: the provisioning
script writes returned keys directly to the private root environment.

Published ports bind to loopback: gateway 4000, Grafana 3000, Prometheus 9090,
Qdrant 6333, Tempo readiness 3200 and Tempo OTLP/HTTP 4318. PostgreSQL is private to the Compose
network. The configured subnet is 172.28.0.0/24; check for conflicts on another
host. The gateway reaches Ollama at the configured Docker bridge address.

Qdrant requires separate administration and read-only API keys. The provisioner
writes them into the private environments; agents receive only the read-only
key. Prometheus requires the `platform` account and its generated password.
Use Grafana for ordinary monitoring: its backend authenticates without exposing
the datasource password to the browser. The provisioner is safe to repeat with
consistent credentials; it refuses disagreements instead of rotating keys.
After repeating it or restoring the environments, recreate Qdrant, Prometheus,
Tempo and Grafana so all bind mounts reference the regenerated files.
See [ADR 0058](../docs/adr/0058-local-service-authentication.md).

Five containers have healthchecks. Tempo's image has no shell; its readiness
is checked through its loopback HTTP endpoint. The operations checker verifies
that Prometheus can scrape its metrics.
A running container alone is not an end-to-end model-health guarantee.

## Aliases and keys

| Alias | Use |
|---|---|
| `local` | All SRE extraction, triage and reasoning |
| `local-embed` | Runbook embeddings and semantic queries |
| `fast`, `balanced`, `smart` | Separate public/synthetic workloads only |

`CONFIDENTIAL_KEY` must allow exactly `local` and `local-embed`. No fallback
leaves either local alias. `ORCHESTRATOR_KEY` is optional for external evaluation;
it is not required by the SRE pipeline. Keys are separate from the master key.

The gateway does not make arbitrary extracted text safe to export. Classification
is assigned by the caller; the SRE caller now keeps all incident content
confidential rather than trusting the extraction model to anonymize it fully.

## Observability and persistence

W3C trace context is forwarded from the agent. Message logging is disabled in
the gateway configuration. Verify this policy after gateway upgrades. The
provisioned dashboard shows service availability, received spans and memory.
Prometheus alert rules stay local until an external receiver is explicitly set.

The five named volumes hold PostgreSQL, Tempo, Prometheus, Grafana and Qdrant
data. `docker compose down` preserves them; `down -v` destroys them and is not a
normal recovery command. See [Operations](../docs/OPERATIONS.md) for backup,
restore testing, retention and migration validation.
