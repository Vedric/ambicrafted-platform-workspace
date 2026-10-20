# ADR 0045 — Cancellable local MCP stdio and backend cleanup

Date: 2026-10-21
Status: Accepted

## Context

The local MCP gateway owns two trusted backend subprocesses. On Python 3.14.7,
MCP SDK 2.2.0 and AnyIO 4.15.1, its SIGTERM regression could pass immediately after
initialization yet fail when the same client waited 250 ms before signalling.
The SDK's default `AsyncFile` stdin reader was blocked in a worker-thread read;
cancelling the gateway did not release that read while the client kept stdin
open. Three isolated idle reproductions exceeded the unchanged ten-second test
bound. Both backend processes exited, but the gateway remained until client EOF.
This was a real shutdown defect, not evidence of a permanently orphaned process
after the client's final cleanup.

A separate adversarial client stopped reading a permitted large response while
keeping stdout open. The SDK's worker-thread write also prevented shutdown.
Closing stdout was insufficient coverage: backpressure on an open pipe is a
different failure mode. Startup and broken-output tests additionally exposed
backend cleanup interrupted by repeated cancellation, or waiting for the startup
timeout before noticing the stop event.

## Decision

Use the SDK's public `stdio_server(stdin=..., stdout=...)` interface with narrow
`AsyncFile[str]` adapters for this gateway's POSIX pipe/socket transport. Keep MCP
JSON-RPC framing and validation in the pinned SDK. Input uses
`asyncio.connect_read_pipe`; output uses nonblocking `os.write` and the public
`loop.add_writer` / `remove_writer` readiness interface. Both directions are
cancellable without abandoning an operating-system thread. Output handles partial
UTF-8 byte writes and returns the character count required by the text interface.
Cancellation abandons the current connection/frame, not a background writer that
could later write into a reused descriptor.

While active, fd 0 is diverted to the null device and fd 1 to stderr so incidental
handler I/O cannot consume or corrupt the MCP protocol. The original descriptors
and their blocking modes are restored on exit, including initialization failures.
The output readiness callback is removed on success, cancellation and error.
Existing gateway logging remains disabled; its CLI reports transport failure
without serializing exceptions, protocol content or environment values.

Shield the backend-owner task join from AnyIO level cancellation. Signal the
existing stop events for ready backends. Cancel an unfinished backend exactly once
when it has not established its session, so its own SDK contexts perform bounded
subprocess cleanup immediately. Keep cleanup in each owning task rather than
closing task-scoped context managers from another task. Keep AnyIO 4.15.1 as an
explicit dependency because the gateway now imports its public interfaces.

Limit incoming JSON lines to 1 MiB excluding the newline. This is a new transport
ceiling, not a claim about an MCP-wide protocol maximum or exact peak memory use.
It is above the gateway's existing 16,384-byte tool-argument limit; that limit,
the 65,536-byte backend inventory limit and the 1,000,000-byte result limit remain
unchanged. An oversized frame closes the connection with a generic CLI error;
no oversized private payload is included in the log. Output framing and existing
result-size enforcement remain unchanged.

## Alternatives rejected

- Raising the ten-second test deadline would hide a blocked I/O operation that
  waits for an unrelated client action; it would not restore cancellation.
- Abandoning a read/write worker or closing/recycling its descriptor elsewhere
  would leave an outstanding operation with unsafe descriptor ownership.
- Forced process exit would bypass the backend-owner cleanup.
- Replacing MCP framing or using private SDK stream claims would enlarge the
  maintenance surface unnecessarily.
- Fixing input alone passed the original tests but failed the independent output
  backpressure counterexample. Both directions need cancellable I/O.

## Consequences and verification scope

This transport targets the supported Linux/WSL deployment and a single gateway
instance per process with pipes or sockets, as used by local MCP clients. Regular
file redirection is rejected; Windows and arbitrary embedded concurrent transports
are not qualified. Tests use Linux `/proc` and pipe-capacity observations to check
owned fixture process identities and actual backpressure. A second interrupt,
SIGKILL, a hostile operating system, and arbitrary untrusted process trees are not
a graceful-shutdown guarantee. The gateway's fixed trusted backend inventory and
read-only authority boundary are unchanged.

Regression coverage includes EOF, broken output, SIGTERM and SIGINT during startup,
idle and an active tool call, sequential gateway restart, concurrent independent
gateways, a full unread output pipe, successful resumed reads, descriptor and
blocking-mode restoration, Unicode, transport failures and oversized input.
Synthetic failures and private diagnostic stacks are retained separately from the
production repository. Qualification of this patch is distinct from the agent's
reasoning quality, security scans, deployment approval and hosted CI.

Primary references: [MCP lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle),
[Python descriptor readiness](https://docs.python.org/3.14/library/asyncio-eventloop.html#watching-file-descriptors),
and the exact installed MCP/AnyIO sources recorded in the private qualification
manifest.
