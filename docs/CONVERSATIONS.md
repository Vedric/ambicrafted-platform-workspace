# AURA conversations and source documents

AURA addresses the operator as **Védric** in English and French and retains French
**vous**. It is a local AI assistant. Conversational instructions favor direct
answers, natural spoken sentences, continuity and one useful follow-up at a time.
This is prompt and audio engineering, not newly fine-tuned model weights or a
guarantee of human-like speech on every utterance.

## In the interface

1. Open **Voice assistant**. Choose the reply language; it initially matches the UI.
2. Type a question, or use **Record** and review its transcript before sending.
   Wait for local model preparation before **Start conversation** enables the
   explicit hands-free loop. Preparation leaves the microphone off. If unavailable,
   select **Prepare conversation** to retry. A spoken turn is sent after a brief
   pause, or at 30 seconds; **Send this turn** sends it sooner. Escape stops it.
   Spoken replies favor at most 55 words and 220 output tokens, with history and
   selected documents retained. Type a message for a more detailed answer.
3. Use **Attach a document or image**, then select the files needed for this turn.
   Attachments remain local. Reopening an existing conversation does not silently
   select its documents again.
4. Open **Conversation history** to search titles/messages and resume a thread.
   Unsent drafts survive thread switching within the mounted workspace, not a
   page reload. **New conversation** starts another thread; deletion is separate.
5. For reusable observations, create a sourced note in **Knowledge → Memory graph**.
   **Use this context with AURA** copies that selected note into a new conversation.
   AURA does not silently search other threads or other customer scopes.

Responses appear progressively. Only complete user/assistant pairs are committed.
If interrupted, retry the unchanged message in the same thread; the operation ID
prevents duplicate saved turns. Retrying a failed spoken message through **Send**
retains its original spoken mode and operation ID. Editing the message, language or selected sources
starts a new operation. Source documents and model replies are untrusted content.
AURA has no action, approval or remediation authority.

## From the terminal

```sh
./plateforme conversations creer
./plateforme conversations lister
./plateforme conversations voir CONVERSATION_UUID
./plateforme conversations joindre CONVERSATION_UUID --fichier /private/evidence.csv
./plateforme conversations dire CONVERSATION_UUID --langue fr --fichier /private/question.txt --piece ATTACHMENT_UUID
./plateforme conversations supprimer CONVERSATION_UUID --confirmer
```

Files must belong to the operator, be regular files without symlinks and have mode
`0600`. Omit `--fichier` for a question supplied on stdin. Confidential text must
never appear in shell arguments/history. The CLI prints the turn UUID on stderr;
reuse it with `--operation-id UUID` when retrying the same request after an
interruption. It outputs a complete JSON reply, not partially saved text.

## Supported formats and explicit limits

Text, Markdown, CSV, JSON, YAML, common code/log text, text PDFs, DOCX, XLSX, PPTX,
PNG, JPEG and WebP are supported. Files are limited to 8 MiB, eight per thread and
two selected images per turn. Images are normalized, stripped of metadata and
limited to 1600 pixels per side; small labels can become unreadable.

PDFs are limited to 100 pages. Scanned PDFs need page images; there is no silent OCR
claim. Spreadsheets include sheet labels and cell references, shared strings and
cached formula results. Formulas and macros never execute. Slides follow the
presentation's relationship order. Unsupported formats return an explicit error.
Office archive expansion, XML entities and parsing time/memory are bounded. The
parser runs in a mandatory **Linux OS sandbox**: read-only runtime/package mounts,
no host home or project files, isolated network/PID namespaces, and a kernel
syscall allowlist that blocks socket creation, fork and execution. It has no
writable temporary storage. Parsed text remains untrusted LLM input.

The API accepts one extraction at a time across all conversations. A competing
upload receives HTTP 409 immediately. Each extraction has a 20-second deadline,
12 CPU seconds, a 1 GiB address-space cap, 64 file descriptors and bounded stdout.
Missing isolation prerequisites return HTTP 503 with no attachment saved; there
is no unsafe compatibility fallback. See [document sandbox operations](DOCUMENT-SECURITY.md)
and [ADR 0032](adr/0032-isolation-systeme-des-documents.md).

History retains at most 500 conversations and 200 complete turns per conversation;
inactive threads expire after 30 days. The UI displays the latest 100 messages.
The model receives up to seven recent prior messages, at most 16,000 characters of
prior text, the 4,000-character question and up to 16,000 characters shared among
selected sources. This is bounded context, not unlimited memory. Extract truncation
is indicated. Stored content is limited to 96 MiB, excluding SQLite overhead.

The private console SQLite backup includes conversations and extracted sources.
Deleting active data does not delete historical backups. Graph notes have a separate
lifecycle; see [Memory](MEMORY.md). Use separate instances, credentials and storage
for separate customer contexts; scope filters do not provide tenant isolation.

## Welcome and technology watch

The public welcome uses fixed local English/French WAVs naming Védric. Browsers may
require a click before any audible playback. The welcome never starts recording.
A fresh cached technology briefing follows it when available, approximately two
minutes including the greeting. Both use the operating system's default speakers.

The running API checks for a refresh every three days from fixed Kubernetes, GitHub
and CISA feeds. Dates and publisher links accompany the local AI summary. Unavailable
sources and stale digests are marked; stale news is not automatically read aloud.
The summarizer rejects unsupported CVE/version identifiers, but this is not complete
fact checking. Read the original linked announcement before acting. Public GETs
read the cache and do not trigger inference. Private notes, documents and conversations
never enter the public digest. Set `PLATFORM_TECH_WATCH=0` in the private configuration
and restart the API to disable scheduled refreshes.

See [Voice](VOICE.md), [MCP gateway](MCP-GATEWAY.md) and
[ADR 0023](adr/0023-conversations-voix-et-memoire.md).
