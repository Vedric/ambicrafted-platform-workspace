# ADR 0051 — Retain the qualified hybrid workstation deployment

Date: 2026-10-22

Status: Accepted for the personal Linux workstation profile.

## Context

The requested outcome is a reliable personal workspace with public source code.
The existing eight container services already cover the gateway, databases and
observability. The authenticated API, CLI, local speech workers and Ollama run on
the host. Document extraction has a separate mandatory rootless namespace and
seccomp boundary. Service exposure and source visibility are separate decisions.

Moving every process into Docker would change local audio/GPU integration,
filesystem ownership, backup access and the nested document-sandbox prerequisites.
No measured capacity or deployment failure currently justifies that migration.

## Decision

Retain Compose for LiteLLM, PostgreSQL, Qdrant, Grafana, Prometheus, Tempo, the
metrics exporter and dedicated Neo4j. Retain locked uv environments and user
systemd supervision for the host application and maintenance tasks. Publish the
repository and qualified source release without opening workstation ports.

Keep the server bound to loopback and the private state owned by one trusted
operator. Preserve the API unit's control-group shutdown and the document
parser's fail-closed isolation. A missing namespace/seccomp prerequisite is an
installation failure, never a reason to run uploads without confinement.

A service update must record its source revision and exact image identity,
preserve a recoverable data baseline, stop affected writers and verify the
result before resuming use. Source files mounted into non-root containers must
retain their intended readable modes; private configuration remains private.

## Alternatives rejected

- An API container with a privileged flag, host Docker socket or disabled parser
  sandbox merely to make nested isolation work: expands authority without a
  demonstrated requirement.
- Kubernetes, multiple API workers or a new distributed database for this
  single-operator profile: introduces an unqualified topology. The current
  SQLite/process ownership and serialized inference are intentional limits.
- Silently migrating the shared Docker host to rootless mode: changes unrelated
  workloads and data ownership. Rootless Docker is a separate deployment option
  with prerequisites and a migration/restore qualification of its own.

## Consequences

The supported server target remains Ubuntu 24.04 amd64, including the qualified
WSL2 setup. Native Windows/macOS servers, another workstation, unattended reboot
recovery and remote multi-user operation require separate acceptance. Browser
portability does not establish server portability.

There are two runtime management paths, Compose and user systemd. The operations
guide must describe both. Public source makes inspection and reproduction
possible; it does not supply credentials, model artifacts, a hosted service or
a claim of autonomous operational expertise.

References: [Docker rootless mode](https://docs.docker.com/engine/security/rootless/)
describes its user-namespace prerequisites;
[systemd process termination](https://www.freedesktop.org/software/systemd/man/latest/systemd.kill.html)
defines control-group shutdown. These references motivate the boundary; the
dated qualification records what was actually tested on this workstation.
