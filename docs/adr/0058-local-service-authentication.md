# 0058 — Authenticate local vector storage and monitoring

Date: 2026-10-24

## Context

An HTTP probe of the installed Qdrant `/collections` and Prometheus
`/api/v1/status/runtimeinfo` endpoints returned 200 without credentials and
reflected an unrelated `Origin` in `Access-Control-Allow-Origin`. Loopback
binding alone did not enforce the intended browser trust boundary. This is an
observed HTTP configuration weakness, not a claim of demonstrated remote
exfiltration or a completed DNS-rebinding attack. Dependency scans do not test it.

## Decision

Use native service authentication and disable cross-origin browser reads.
Qdrant requires an administrative API key for indexing/snapshot maintenance and
a separate read-only key for agents, MCP retrieval, console search and metrics.
The MCP environment allowlist never forwards the administrative key.

Prometheus uses its native web configuration with a bcrypt verifier. The CLI,
control API, self-scraper, Grafana backend and Tempo remote writer authenticate.
The Prometheus healthcheck uses `promtool check ready` with a client configuration;
successful process startup alone does not satisfy readiness. Grafana stores its
datasource password as a secure field; browsers receive neither service secret.

`scripts/securiser_services.py` generates independent random credentials directly
into private root/gateway environments. It preserves existing credentials,
refuses mismatches and unsafe paths, and serializes root environment updates
with the control plane. It does not perform implicit credential rotation.
Container-readable files live inside a host directory accessible only to its
owner; only individual files are mounted read-only into the containers that
need them. Missing files fail startup instead of being created as directories.
LiteLLM receives an explicit environment allowlist, rather than every gateway
credential. Backups preserve the environments; the generated mounts can be
recreated after restoration. Disposable restore targets also require a fresh
Qdrant credential.

## Alternatives rejected

- CORS changes alone: they constrain browser reads but do not authenticate API
  clients or prevent unauthenticated direct writes.
- An additional reverse proxy: both affected services already support native
  authentication; another daemon is unnecessary for this local boundary.
- One Qdrant key for every component: retrieval agents do not need write access.

## Consequences

Install `apache2-utils` for `htpasswd`, run the provisioner before starting the
gateway, and recreate affected containers after provisioning or restoring
mounts. Credentials stay out of command arguments and operator output.
Prometheus direct browsing now requires the `platform` account; Grafana remains
the normal authenticated monitoring entry point. Qdrant's direct dashboard
requires its own key; it no longer grants anonymous data access.

Transport remains local HTTP on loopback and the private Compose network. This
does not provide TLS, tenant isolation, protection against a compromised OS
account/Docker administrator, or authentication for Tempo's local receiver.
A remote deployment needs a separately qualified ingress, TLS and identity
design. Existing human approval gates and model accuracy limitations remain.

The disposable qualification exercises actual refusal of anonymous/wrong-key
requests, read-only write denial with no collection created, search, snapshot
restore, all five scrape targets, Grafana queries, real Tempo remote-write and
restart persistence. Unit tests separately check secret scoping and provisioning
failure paths. Earlier failed fixture runs remain part of the private evidence.

References: [Qdrant security](https://qdrant.tech/documentation/security/),
[Prometheus authentication](https://prometheus.io/docs/guides/basic-auth/),
[Tempo remote-write configuration](https://grafana.com/docs/tempo/latest/configuration/).
