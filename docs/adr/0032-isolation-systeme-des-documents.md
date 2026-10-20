# ADR 0032 — OS-enforced isolation of attachment extraction

Date: 2026-10-20
Status: Accepted for the private Linux/WSL deployment; exact-release qualification
is recorded separately.

## Context

Conversation attachments include PDF, Office archives and native image codecs.
The prior disposable subprocess had CPU/memory limits and a Python audit hook,
but retained the operator's filesystem access. Native code could bypass that
hook. Also, `StreamReader.limit` did not bound the bytes retained by
`Process.communicate()`.

The API already has one upload lock shared across all conversations, rejects
busy requests immediately, authenticates uploads and limits each input to 8 MiB.
Adding an independent queue or a worker service would not fix the missing
security boundary.

## Decision

Launch each parser through rootless **bubblewrap**, with mandatory user, network,
IPC and PID namespaces, disabled nested user namespaces and no capabilities.
Use a new session and `--die-with-parent`. Expose only a trusted Python runtime,
system libraries, the worker file and individual parser packages as read-only
mounts. The host home, checkout, `.env`, host `/proc`, Docker socket and other
application packages are absent. The root and `/tmp` are read-only. The only
device mounted is `/dev/null`. Clear the environment and close inherited file
descriptors.

Start Python with `-I -S`, excluding environment-dependent imports, site startup
and editable-install `.pth` files. Load only the explicitly mounted
`PIL`, `pillow.libs`, `pypdf` and `defusedxml` packages.

Before consuming stdin, install hard resource limits and a **default-deny
libseccomp syscall filter**. It admits single-process parsing operations;
socket creation, execution, fork/clone, namespace changes, tracing and
`io_uring` are not admitted. This remains enforced if a native codec is
compromised. libseccomp resolves names for the native ABI rather than embedding
architecture-specific syscall numbers.

Bound stdout while reading it, rather than checking only after accumulation.
Retain the 20-second parent deadline and cancellation cleanup, including
cancellation while the subprocess transport is being created. Retain the
existing single shared upload admission lock.

There is **no unsandboxed fallback**. Missing bubblewrap, missing libseccomp,
unsupported namespaces or sandbox setup failure produce HTTP 503; no extracted
attachment is persisted. Rejected/oversized documents produce HTTP 422.

## Alternatives rejected

- Python audit hooks alone: native calls can bypass them.
- A hand-written namespace launcher using `unshare` and mount syscalls:
  unnecessary bespoke privileged setup compared with the maintained bubblewrap.
- A Docker daemon per attachment: substantially larger permissions and
  operational dependency for this single-user subprocess boundary.
- A writable temporary filesystem: the parsers work in memory; even a private
  tmpfs would need a separate storage limit and is unnecessary.
- Windows/macOS silently using the old subprocess: that would make the security
  claim depend on an unsafe fallback. Those hosts must run the API in the
  supported Linux environment, such as WSL2.

## Consequences and validation

Deployment needs the OS packages `bubblewrap` and `libseccomp2`, Linux namespace
support and a dedicated Python venv. Security updates for these system packages
remain part of host maintenance. Containers or AppArmor policies that forbid
rootless user namespaces require an explicitly supported configuration; do not
disable confinement globally to bypass an error.

The boundary adds a short subprocess setup cost per upload. New parser
dependencies or system-call requirements require a reviewed allowlist change
and the real sandbox regression tests.

Tests exercise synthetic input through the real kernel boundary: native
`ctypes` attempts to read an operator-readable canary, access home/host `/proc`,
write root/tmp/runtime, create TCP/Unix sockets, fork, exec, create a namespace
and use an inheritable host file descriptor. They verify denial and scrubbed
environment, successful image/Office/PDF extraction, limits, output flooding,
timeouts, cancellation during startup, missing sandbox behavior and global API
admission across different conversations.

This is not a VM boundary, an independent penetration-test certification, malware
classification, or proof against a kernel/runtime/bubblewrap vulnerability. The
trusted runtime/system-library mounts and shared host kernel remain part of the
trusted computing base. Parsed text is still untrusted data for the LLM, and
source instructions must not grant it tools or approval authority.

## References

- [Bubblewrap namespace and security model](https://github.com/containers/bubblewrap)
- [libseccomp filter initialization](https://man7.org/linux/man-pages/man3/seccomp_init.3.html)
- [libseccomp rule semantics](https://man7.org/linux/man-pages/man3/seccomp_rule_add.3.html)
