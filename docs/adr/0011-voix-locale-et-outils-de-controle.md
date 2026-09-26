# ADR 0011: offline voice and explicit control tools

Date: 2026-09-26. Status: accepted.

## Context

The owner requests a French feminine conversational voice, microphone input,
useful MCP integrations and specialist agents. Customer data must stay local.
Browser speech recognition is not an acceptable default because its implementation
may send audio to an external service. Adding arbitrary third-party tools would
also expand the agent's authority beyond the reviewed incident contract.

## Decision

- Speech input and output run in a separate, pinned Python 3.13 environment.
  Piper uses the French feminine SIWIS voice; faster-whisper transcribes French
  on CPU. Artifact revisions and SHA-256 hashes are versioned. Runtime model
  downloads are forbidden; installation is a distinct operation.
- The browser records only after an explicit microphone gesture. Audio is capped
  at 8 MiB and 90 seconds. The operator can stop recording, review and edit the
  transcription before sending it. Automatic playback is opt-in and has a stop
  control. A complete text interface remains available.
- The control plane runs one speech operation at a time, with private temporary
  files, a 130-second outer deadline and process-group cleanup. Audio is removed
  after each operation. Native decoder diagnostics are suppressed to prevent
  accidental disclosure of input content.
- Conversation uses the confidential gateway key and the `local` alias. History
  is bounded and kept in page memory. Conversation never has approval or execution
  authority; its responses are explicitly distinct from a sourced incident report.
  It shares the inference lock with incident work to prevent GPU contention.
- The existing specialist graph performs extraction, triage, tool-based
  investigation and human supervision. It is sequential and bounded. We do not
  simulate an autonomous fleet or let agents approve each other's proposals.
- A separate stdio MCP adapter exposes read-only service health, analysis metadata
  and runbook inventory. The original runbook MCP remains the investigation tool.
  Runbook editing, index publication, backups and restoration tests require an
  authenticated operator operation through the shared CLI/UI API.

## Consequences

The workstation needs about 550 MB of speech artifacts and a separate runtime.
CPU speech avoids taking GPU memory from analysis, but recognition and playback
have measurable latency. Transcription can be wrong, especially for identifiers;
operator review remains necessary. Voice licensing and attribution are documented
in [VOICE.md](../VOICE.md). Audio-format tests include real WAV, WebM/Opus and
Ogg/Opus round trips with networking disabled.

The optional MCP adapter is a trusted local process: possessing the private
control-plane credential is an authority boundary, even though its published
tools are read-only. Remote multi-user MCP access is outside this deployment.

## Alternatives rejected

Cloud browser recognition, external voice APIs, speculative plugin installation,
and unrestricted shell/browser tools for the incident agent were rejected because
they do not fit the approved local confidentiality and human-decision boundary.

## Verified local output control

The installed gateway maps `reasoning_effort: none` on the `local` alias to
Ollama's `think: false`. The incident client and voice conversation set it
explicitly. Qualification caught an extraction that exhausted 3,000 output
tokens before producing parseable JSON with the implicit model default. The
explicit setting preserves the output budget for the structured answer.
The repeat qualification completed both approval and rejection, and reduced
the measured short dialogue from 76.5 seconds to 1.4 seconds on this workstation.
These are individual observations, not latency guarantees or quality benchmarks.

Reference: [Ollama thinking controls](https://docs.ollama.com/capabilities/thinking).
