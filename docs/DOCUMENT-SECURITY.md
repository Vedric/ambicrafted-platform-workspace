# Document extraction: isolation and operations

Both UI and CLI attachments use the same authenticated API and OS-isolated
parser. This feature requires **Linux or WSL2, a dedicated Python virtual
environment, bubblewrap and libseccomp**. Native Windows/macOS API execution is
not supported for attachment extraction; use the Linux environment.

## Install and verify

On the supported Ubuntu environment, use signed distribution packages:

```sh
sudo apt-get update
sudo apt-get install bubblewrap libseccomp2
bwrap --version
```

Bubblewrap must support `--disable-userns` and `--assert-userns-disabled`
(0.8 or later). Distribution updates must be applied regularly. The exact
qualification records the version tested; the application does not download or
execute a replacement binary at runtime.

The control API's service `PATH` must include the installed `bwrap`. Test the
actual environment, rather than assuming support from a kernel version:

```sh
cd apps/control-api
uv sync --locked
uv run --locked pytest tests/test_document_sandbox.py tests/test_documents.py tests/test_conversations.py -q
```

These tests exercise real rootless namespaces and the kernel syscall filter,
using only generated synthetic documents. No confidential document is uploaded
to an external service. The tests require namespace support; they intentionally
fail if the security boundary cannot be established.

## Troubleshooting

| Result | Meaning and operator action |
|---|---|
| HTTP 503, secure document processing unavailable | Verify `bwrap` is on the service PATH, libseccomp2 is installed, and user/network/PID namespaces are permitted. No file is persisted. |
| HTTP 409, another document is being processed | One extraction is already active across the instance. Retry after it finishes. There is no hidden extraction queue. |
| HTTP 422, safety/time/output limit | Use a smaller, valid, unencrypted document. Export scanned PDF pages as images. Do not raise limits to accept an unexplained malformed file. |
| HTTP 415 | Choose a documented supported format; renaming the extension does not convert the content. |

Some hardened/containerized distributions restrict rootless namespaces through
AppArmor or their runtime. Qualify the service under that policy or run it on the
supported Linux/WSL host. **Do not make bubblewrap setuid, globally disable
AppArmor, use privileged containers, or add an unsandboxed fallback.**

On Ubuntu 24.04, installing bubblewrap alone may leave its user-namespace
permission unavailable. The signed `apparmor-profiles` package supplies the
opt-in `/usr/share/apparmor/extra-profiles/bwrap-userns-restrict` policy.
It authorizes `/usr/bin/bwrap` to establish namespaces and places its executed
children under a capability-denying profile. Have the host administrator review
this policy and existing profiles before installing/loading it; do not replace
a custom profile blindly. It does not authorize a private `~/.local/bin/bwrap`.
See [Canonical's explanation](https://discourse.ubuntu.com/t/understanding-apparmor-user-namespace-restriction/58007).

The GitHub Ubuntu 24.04 jobs run `scripts/qualifier_sandbox_ci.sh` before API or
browser tests. Its first probe uses the production launcher with one fixed
synthetic byte and records the kernel settings and bounded worker stderr. On a
restricted GitHub runner only, a failed probe can load that distribution profile,
then must pass the same probe. Existing different profiles are preserved; global
sysctls and application isolation are unchanged. `--probe` is a read-only local
diagnostic. This detailed stderr path must never be used with operator documents;
the API deliberately keeps its production errors generic.

After setup changes, verify a successful upload and a rejected invalid document
through the UI/CLI. Re-run the kernel boundary tests when changing Python,
Pillow, pypdf, libseccomp, bubblewrap or the hosting environment.

**Readiness → Runtime → Document sandbox** invokes the same sandbox using a fixed
one-byte synthetic text document, with a five-second deadline and the normal
30-second readiness cache. No conversation, private input or attachment is read
or saved. Failure marks document ingestion unavailable and overall readiness
failed; the independent analysis capability remains separately reported. This
functional probe is not the adversarial kernel regression suite.

## Security boundary and remaining limits

The parser sees only trusted runtime/system libraries, the worker and three
selected parser packages. It cannot see the API's home, checkout, `.env`, host
`/proc` or Docker socket. Input/output flow through anonymous pipes, not paths.
The root filesystem is read-only, including `/tmp`; no host temporary files are
created. Core dumps are disabled. Environment variables and inherited
descriptors are not passed into the parser.

The native syscall filter prevents network sockets, process creation, execution
and namespace changes. The parent drains stdout with an explicit bound and
kills/reaps the sandbox on timeout, output overflow or cancellation. API upload
admission is global to the one supported control process; it is not a distributed
multi-instance queue. At most one coalesced synthetic readiness probe can coexist
with that one attachment extraction.

The shared kernel, bubblewrap, trusted runtime and native dependencies remain
part of the trusted computing base. This is not malware detection or proof
against every kernel exploit. Extracted instructions, formulas, links and prose
remain untrusted source material. AURA does not acquire execution, remediation
or approval permissions from a document. See [ADR 0032](adr/0032-isolation-systeme-des-documents.md).
