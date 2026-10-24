# ADR 0056 — Disable native voice telemetry before initialization

Date: 2026-10-24. Status: Accepted for the local voice process.

## Context

Qualification in a fresh clone with a minimal environment found a new
`:memory:.ses` file in the voice working directory. Isolated import probes
reproduce it with ONNX Runtime and Piper, but not with AV, faster-whisper or
CTranslate2. No real speech or client document was used in those probes.

The pinned ONNX Runtime 1.30.0 native build includes Microsoft's 1DS telemetry
provider. Its privacy documentation requires `ORT_DISABLE_TELEMETRY=1` **before
initialization** to prevent the uploader, events and persistent identifier.
The later disable-events API may leave an initialization event. Hugging Face's
separate offline/telemetry settings do not control this native library.

## Decision

Set the native opt-out unconditionally when the `voix_locale` package loads,
before any of its modules can import Piper or ONNX Runtime. Reassert it in the
existing offline-engine bootstrap. The control API also supplies it explicitly
to the clean child-process environment, covering both CLI and resident workers
before Python starts. Contradictory inherited settings cannot opt this private
voice service into telemetry.

Keep the package's native engines, pinned models and CPU backend unchanged.
Do not merely ignore the generated file or remove it after initialization. Do
not rely on Python socket mocks: native HTTP clients do not use those functions.
Do not change unrelated user shell preferences or the system-wide environment.

## Alternatives rejected

- Rely on an operator's environment setting: it disappears in a minimal service
  environment and the API deliberately filters inherited variables.
- Call `disable_telemetry_events()` after importing Piper: too late for the
  documented initialization boundary.
- Treat successful network-isolated inference as proof that the native library
  never attempts telemetry in an ordinary networked process.
- Rebuild ONNX Runtime without telemetry: a larger native-build maintenance
  obligation than the documented lifetime opt-out, without a demonstrated need.

## Verification and limits

Fresh subprocess tests import the package, CLI, resident worker and synthesis
entry points with a deliberately contradictory setting, then initialize the
real native library. No persistent state may appear in the temporary working
directory. The resident API test verifies the child receives the opt-out before
its first request. The existing backend-bootstrap check remains in place.

A temporary verified Ubuntu strace 6.8 tool observes native system calls in
network-isolated processes. The old import creates the session file; the fixed
import does not. The fixed probe records zero IPv4/IPv6 socket creations, while
a separate socket control is detected. The short old probe also records zero
IPv4/IPv6 sockets: **this observation does not establish historical data
transmission or its absence**. Actual model synthesis/transcription still needs
its separate offline qualification after this change.

This guarantee concerns platform-controlled process startup. Importing ONNX
Runtime in an unrelated embedding application before importing this package
cannot retroactively undo that application's earlier initialization.

Reference: [ONNX Runtime privacy and runtime opt-out](https://github.com/microsoft/onnxruntime/blob/v1.30.0/docs/Privacy.md).
