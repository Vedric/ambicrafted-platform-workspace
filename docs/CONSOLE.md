# Private console and CLI

Ambicrafted provides one authenticated local control API for the graphical
console and the `./plateforme` CLI. It binds to **127.0.0.1:8787**, runs one
analysis at a time, and requires an explicit human decision before delivering
an actionable diagnosis. It does not execute proposed remediation commands.
This deployment supports one trusted workstation operator. Remote publication,
multiple tenants and high availability require a separate design.

## Interface and motion

The welcome page and authenticated workspace offer English and French through
the interface language selector. English is the default; the browser remembers
the choice. Navigation, forms, status/error messages and accessibility labels
follow that selection. Runbooks, alert titles, generated diagnoses and transcripts
retain their content and language. CLI commands and API identifiers remain stable.
AURA's English/French conversation selector is independent: changing the interface
does not change the voice or silently translate client evidence. Page names below
use the English labels.

Menus, descriptions, controls and supporting labels use a larger reading scale.
Small text is sized in `rem` so browser font preferences remain effective;
browser zoom is available without changing the application's language or state.
Desktop and mobile layouts are checked with Playwright after typography changes.

The welcome screen, overview and AURA use a consistent visual identity. Ambient
motion uses transforms and opacity; pointer parallax applies only to a mouse.
Offscreen orbital scenes and background tabs pause their CSS animations.
Animations are automatic; there is no Motion on/off button or appearance setting.
Old browser overrides are removed. The operating system's reduced-motion setting
remains authoritative for accessibility. AURA, charts, architecture paths, scroll
fades and page transitions share that preference. Offscreen scenes and hidden
tabs pause to avoid unnecessary rendering. See
[ADR 0048](adr/0048-observabilite-correlee-et-mouvement.md) for this change;
older motion reports describe their historical release behavior.
After updating, reload the page to load the new assets. Navigation remains available by keyboard, with a command menu on
`Ctrl+K` / `Cmd+K`, a focus-trapped mobile menu and a skip-to-content link.

The overview's **Operational pulse** charts show recorded activity over seven or
fourteen UTC days, current saved run states and the latest service probe durations.
Runs include investigations and maintenance operations. Deleted runs disappear
from these aggregates. Use **Inspect a day** with the keyboard or open **View chart
data** for the exact values. Health probe durations describe a local HTTP check;
they are not model response times or an availability SLO.

**Architecture** explains the investigation, voice, knowledge and telemetry paths.
Select a path and a component to inspect its purpose and boundaries. Animated
connections illustrate the documented design; service-health labels use live probes.
Scroll fades work in either direction without moving interactive controls. They stop
with the system reduced-motion preference, hidden tabs or keyboard focus. They do not gate access to content.

## Install and start

Run from the checkout root, with the pinned Node/npm versions declared in
`apps/console/package.json` and `uv` available. First install the
[Linux host prerequisites](HOST-TOOLS.md): bubblewrap, libseccomp2 and working
unprivileged namespaces are mandatory for document extraction.

```sh
uv sync --locked --all-extras --project agents/sre-agent
uv sync --locked --project mcp-servers/runbooks
uv sync --locked --project apps/control-api
cd apps/console
npm ci
npm run build
cd ../..
./plateforme prerequis
./plateforme servir
```

The wrapper also finds `~/.local/bin/uv` when it is not on `PATH`. It resolves
the checkout from its own location, so it works from another current directory.
Do not move an installed checkout without reinstalling the user service.
The generated service explicitly searches `~/.local/bin` before standard system
tool directories. `servir` and service installation fail before startup if the
real synthetic extraction probe fails. The probe runs again inside the systemd
service's isolation constraints; no parser fallback disables isolation.
The gateway, local inference service and knowledge index must be configured as
described in [operations](OPERATIONS.md). Starting the console does not silently
start Docker services or send confidential workloads to a remote model.

From a second terminal:

```sh
./plateforme ouvrir
./plateforme statut
./plateforme preparation
./plateforme parametres
```

`ouvrir` requests a single-use, 60-second ticket and passes it directly to the
local browser. It never prints the ticket or the authenticated URL. The browser
exchanges it for an HttpOnly, SameSite=Strict session and removes the fragment.
The root `.env` contains the generated API key and must belong to the current
user with mode 0600. Do not copy a session URL, expose the port through a tunnel,
or include `.env` in a support archive. All assets are served locally.

On WSL, `ouvrir` uses the Windows browser through `cmd.exe` when `BROWSER` is
unset. Launcher output is suppressed so it cannot print the ticket URL.
On another workstation without a configured launcher, configure Python's
`BROWSER` integration for the installed browser. A password is another local
entry method:

```sh
./plateforme mot-de-passe
```

The interactive prompt does not echo the password. Use 14–128 characters; the
server stores a scrypt hash and revokes existing sessions after a change. For
automation, `mot-de-passe --stdin` accepts the password from a protected input
stream. Never put a password or an API key directly in command arguments.
Then open `http://127.0.0.1:8787` and use the login form. Sessions last 12 hours.

## Recover direct browser access

After the first `./plateforme ouvrir`, select **Set up browser access** in the
banner, or **Settings → Console password**. Choose and confirm a 14–128 character
password. Saving it revokes old sessions and returns to sign-in. Thereafter,
open the same loopback address and sign in from Welcome; successful password
entry immediately opens the workspace. The CLI continues to use its private API
key or one-use ticket. No password is generated or exposed by the frontend.

If Welcome shows **Set up browser access** rather than a password form, no password
has been configured for this platform state. If a previously open session has
expired, run `./plateforme ouvrir` once to access the authenticated setup. Use the
same browser hostname consistently: `localhost` and `127.0.0.1` have separate
cookies and microphone permissions. Authentication is never disabled to recover
an expired session.

## Microphone, sound and walkthroughs

AURA uses the operating system's default microphone and speakers. Device selectors
have been removed from Welcome and AURA, and older saved selections are ignored.
Choose the intended input/output in Windows/Linux/macOS audio settings first.

1. Open **Check microphone & sound** and select **Test microphone**. Allow the
   browser permission when requested. Visiting the page does not capture audio.
2. Speak, watch the meter, stop and select **Listen to the sample**. This diagnostic
   stays in the browser and never uploads the sample. If silent, check hardware
   mute, OS privacy, browser site permissions and the default device in OS settings.
3. Select **Record**, then **Finish recording**, review the transcript and **Send**.
   **Start conversation** explicitly enables successive spoken turns. **Escape**
   stops capture, processing and playback. Speech never approves infrastructure work.
4. Welcome audio, music, AURA and guide videos use the same system output. Check
   tab volume and system volume if silent. A browser may require a click before
   autoplay: use **Listen to my welcome** or the video play control.
5. Open **User guide** for narrated, locally served walkthroughs. Choose the
   interface language, use native play, volume, speed and fullscreen controls,
   and switch captions on or off. Each lesson has a complete text transcript.
   Demonstrations use synthetic data and simulated agent responses; they explain
   the workflow without claiming model accuracy.

The UI language and speech language are independent. AURA's resident local voice
worker reduces repeated model startup after the first exchange. It releases its
models after five idle minutes, and cancellation discards pending audio. See
[voice details](VOICE.md) for limits and native tests. Physical audio quality,
permissions and perceived naturalness still need a check on your actual machine.

## First operator session

1. Set your interface language and theme. Use the top-bar command menu to move
   between pages, or the navigation drawer on a small screen.
2. Open **Readiness**. Review required failures or unavailable checks, then
   inspect **System health** for the underlying services. Suggested commands
   are guidance to review, not automatic fixes.
3. Review **Runbooks** and use **Search** with synthetic queries. Edit only
   reviewed sources, then reindex explicitly from **Operations**.
4. Open **Missions** and choose an incident, performance, capacity or regression
   brief. It opens an editable **New analysis** form; replace prompts with
   observations before selecting **Run analysis**. A preset never submits itself.
5. Follow the analysis stages, inspect complete sources and prerequisites, then
   decide from **Approvals**. Export the result only after reviewing its status.
   AURA can help frame a question, but cannot approve or execute a proposal.

All mission presets enter the same local SRE pipeline. They are not autonomous
specialist deployments, client connections or tenant boundaries. For real client
work, use the [mission walkthrough](CLIENT-WORKFLOW.md), including a separately
qualified environment and private handover/retention arrangements.

## Measured readiness

```sh
./plateforme preparation
./plateforme doctor
```

Both aliases call authenticated `GET /api/preparation`; the UI reads the same
result. Nineteen checks cover installed runtimes, private file permissions,
actual loopback API listeners, configured local destinations, live restricted
model aliases, six services, source/index availability, English/French voice
artifacts and real handshakes with both MCP servers. No diagnostic sends client
text to a model, downloads a package or runs a repair command.

Results include timestamps, evidence, required/optional status and per-feature
prerequisites. Independent probes have a 20-second deadline; the combined result
is cached for 30 seconds, with underlying health/voice caches described in
[TOOLS.md](TOOLS.md). Exit code 2 indicates an incomplete readiness result. The
API must already be running; use the service-manager commands below if it is not.

An all-green checklist means measured local operational prerequisites are met.
It does not establish model accuracy, index freshness, microphone behavior,
restorability, vulnerability resolution or production security approval.

## User service

After building the UI and installing the locked environments:

```sh
./plateforme installer-service --demarrer
systemctl --user status ambicrafted-console.service
```

Without `--demarrer`, installation only writes the unit and reloads the user
manager. The generated unit uses the current checkout, loopback-only API,
`NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=full`, a private umask and
`KillMode=control-group`. The web server disables access logs and forwarded
proxy headers. Credential values are not embedded in the unit.

The service restarts after failure and stops its own child processes. A restart
marks unfinished jobs as interrupted rather than replaying raw alerts.
The user manager must remain available: this is not a guarantee against host
shutdown or WSL termination. A user service with `PrivateTmp` requires the host
to support user namespace and mount isolation. When systemd reports repeated
start failures, clear its rate limit before investigating:

```sh
systemctl --user reset-failed ambicrafted-console.service
systemctl --user status ambicrafted-console.service
journalctl --user -u ambicrafted-console.service --since today
```

After a reviewed update or checkout move, rebuild with the locked dependencies,
run the tests and reinstall with `installer-service --remplacer`. An unrelated
unit or symlink is not overwritten. To stop and disable the service:

```sh
systemctl --user disable --now ambicrafted-console.service
```

## Analyze and decide

Raw alerts are accepted on stdin or from a private UTF-8 file; they are never
passed to the agent in process arguments. Choose a short title without secrets.
The following example refers to an existing operator-owned file:

```sh
chmod 600 /private/path/alerte.txt
./plateforme analyses creer --titre 'Incident PostgreSQL' --fichier /private/path/alerte.txt --attendre
./plateforme analyses lister
./plateforme analyses voir IDENTIFIANT
./plateforme analyses approuver IDENTIFIANT --attendre
./plateforme analyses refuser IDENTIFIANT --attendre
```

Replace `IDENTIFIANT` with the 32-character ID returned by the API. Approve only
after checking source provenance, applicability, prerequisites and rollback.
Similarity is not confidence and a source match does not establish that a
procedure fits the live incident. Approval and refusal are mutually exclusive;
a concurrent or repeated decision is rejected.

`--attendre` stops at a stable state, including a pending human decision. Its
default limit is 1,200 seconds; `--delai` changes only the CLI wait, not the
agent's execution budget. Interrupting the CLI or reaching that deadline does
not cancel a submitted job. To cancel an active or queued job explicitly:

```sh
./plateforme analyses annuler IDENTIFIANT
./plateforme analyses attendre IDENTIFIANT --delai 300
./plateforme analyses exporter IDENTIFIANT --format md --sortie /private/path/rapport.md
./plateforme analyses supprimer IDENTIFIANT --confirmer
```

Exports create a new file with mode 0600 and refuse to overwrite an existing
file. Deleting an inactive analysis also removes its own checkpoint directory;
copies, exports and backups have their own retention. Structured results go to
stdout, operational errors to stderr. Exit code 0 means the CLI operation
succeeded; 1 indicates an access/input/transport failure; 2 indicates a returned
failed, interrupted or budget-exhausted analysis, incomplete readiness, or invalid CLI arguments;
130 indicates an interrupted CLI. Inspect the returned `statut` before taking
an automation decision.

Raw alert input remains in the bounded in-memory queue and child stdin. Derived
analysis content and graph checkpoints can remain confidential. Console state
is held below `~/.local/state/ambicrafted` in private directories. Do not attach
these databases or screenshots of real incidents to public issues.

## Knowledge and operations

```sh
./plateforme runbooks lister
./plateforme runbooks lire incident-p1-database.md
./plateforme runbooks ecrire procedure.md --fichier /path/procedure.md --empreinte ''
./plateforme operation indexer --attendre
./plateforme operation verifier --attendre
./plateforme operation sauvegarder --attendre
./plateforme operation tester-restauration --attendre
./plateforme observabilite
```

Use a filename returned by `runbooks lister`. An empty `--empreinte` creates a
new document; to update one, pass the SHA-256 `empreinte` returned by `lire`.
An intervening edit causes a conflict instead of overwriting someone else's
version. Markdown documents are limited to 8,000 characters, and only confined
regular `.md` files are accepted. Editing remains an explicit human action.
Reindex after reviewing content changes; a stale semantic index is not silently
trusted. Search accepts its query on stdin:

```sh
printf '%s' 'connexions PostgreSQL' | ./plateforme recherche --mode texte
printf '%s' 'connexions PostgreSQL' | ./plateforme recherche --mode semantique
```

Only the listed operational commands can be queued; the API provides no generic
shell endpoint. They share the same serial worker as analyses. Restore testing
uses the most recent eligible local backup in disposable resources, not the
running database. See [operations](OPERATIONS.md) for backup content, retention,
rollback and the limits of restore validation.

## AURA conversation and local voice

Send or clear an existing draft before starting hands-free mode. The text composer
is disabled while the spoken loop is active; ending the conversation restores it.
This prevents an automatic transcript from overwriting a draft you were editing.


Install the separate speech runtime and pinned English/French artifacts following
[VOICE.md](VOICE.md). AURA identifies itself as an AI assistant. Audio processing
is local, speech uses CPU, and dialogue uses the confidential `local` model path.
Conversations are saved in private local SQLite with bounded history and retention.
See [AURA conversations](CONVERSATIONS.md) for source documents, CLI commands,
retry behavior and explicit memory boundaries.

The default manual flow is **Record**, stop recording, review/edit the transcript,
then **Send**. **Listen** plays a reply through the selected female synthetic
voice. The conversation-language selector defaults to English and also offers
French independently of the interface language.

On entering AURA, the authenticated local model is prepared with a fixed one-token
request. The microphone stays off and **Start conversation** waits for readiness.
A cold start can take a couple of minutes. If the model is busy or unavailable,
**Prepare conversation** offers an explicit retry. The local request asks the runtime
to retain the model for 24 hours; another workload or a restart can still unload it.

Explicitly start hands-free conversation and grant microphone permission to use
successive spoken turns. Browser input-energy detection ends a spoken turn
after approximately 1.1 seconds of silence once speech was detected. AURA
transcribes, sends that turn, generates a reply, speaks it and resumes listening.
A turn is sent after at most 30 seconds of detected input, even if background noise
prevents a pause. **Send this turn** sends earlier. Without detected input, capture
stops after 12 seconds and any transcription remains available for manual review;
it also pauses after 20 completed turns. Spoken replies target at most 55 words and
220 output tokens; typed replies retain their 650-token budget.
A conversational transcription or synthesis is stopped after 30 seconds, and
model generation after 45 seconds. The UI names the failing stage. The typed
message is preserved if generation fails; a completed written answer survives a
voice failure. Retry does not silently run in the background.
These are bounded sequential steps, not simultaneous streaming or listening
during playback. Device load and model initialization can introduce delays.

Use **End conversation** or Escape to end the session. **Speak now** interrupts
reply playback before reopening the microphone for another turn; it is not
simultaneous listening. Hiding the tab or leaving
the page cancels pending browser work, stops recording/playback and releases the
microphone. The conversation-language selector is disabled during active work.
Automatic submission is limited to an explicitly started conversation; manual
recording lets you review before sending. A spoken “yes” never approves an
analysis or authorizes an operation.

The voice commands use the same authenticated API as the console:

```sh
./plateforme voix statut --langue en
./plateforme voix statut --langue fr
printf '%s' 'Bonjour, la plateforme est disponible.' | ./plateforme voix parler --langue fr --sortie /private/path/bonjour.wav
./plateforme voix transcrire --langue fr /private/path/question.webm
```

`parler` accepts at most 2,000 characters from stdin or `--fichier` and writes
a new WAV file with mode 0600. Audio bytes are never printed to the terminal.
`transcrire` accepts an operator-owned private audio file, at most 8 MiB; the
server also enforces a 90-second recording limit after decoding. The transcript
is returned as JSON. Symlinks, pipes and non-private files are refused. A text
file supplied for synthesis must also be private. Neither operation sends
content to an external speech service.

Voice availability depends on the separately installed, pinned local speech
runtime and model artifacts. `voix statut` reports their availability; the CLI
does not silently download models or substitute a cloud service. A transcription
is editable input, not authorization to execute a command or approve a diagnosis.

## Read-only control MCP

The repository's `.mcp.json` declares NEXUS as its single MCP entrypoint. Start the
authenticated local API before connecting its complete operator profile:

```sh
uv run --locked --project apps/control-api python -m plateforme.passerelle
```

The gateway exposes eleven control tools: health, readiness, catalogue, analysis list
and detail, runbook list and read, search, bounded audit and two scoped memory reads.
Its runbook profile exposes four source/search tools. [MCP-GATEWAY.md](MCP-GATEWAY.md)
lists namespaces, authority and transport bounds. Dedicated memory requires its
separate Neo4j installation.

The private key is read internally; never put it into an MCP configuration or
command line. Missing credentials/state return an unavailable result rather than
being initialized by MCP. There is no approval, shell, editing or remediation
tool. Relative paths in `.mcp.json` require the checkout root as the client working
directory. Connect confidential tools only to a trusted local consumer; a remote
consumer can transmit the content it receives.

## Semantic search freshness

Semantic results are checked against the current source corpus and exact indexed
passages, with a minimum relevance score of 0.60. Editing, adding or removing a
runbook can make the published index stale. Search then reports unavailable until
you explicitly reindex the reviewed corpus under Operations. Literal search remains
available and a search request never rebuilds the index automatically. Provenance
checks do not establish the factual accuracy of a runbook or model diagnosis.

The console validation accepts at most 1,000 directory entries, 200,000 bytes per
Markdown file, 8,000,000 source bytes in total, 10,000 fragments and 8,000,000
expanded fragment characters. Oversized or unstable snapshots are unavailable;
splitting repeated or excessively long sections is preferable to weakening these
bounds. See [ADR 0019](adr/0019-provenance-recherche-console.md).

## Maintenance and qualification

Run the API unit and integration suites, the frontend build and browser tests
from the exact commit being delivered. CI results from an uncommitted checkout
are not release evidence. Run real local inference and a restore drill as
separate workstation acceptance checks; deterministic tests do not measure
model correctness, incident coverage or GPU latency.

The console is a control plane for a bounded assistant. Review the outstanding
image advisories in [dependency findings](DEPENDENCIES.md), corpus coverage and
representative incident evaluations before expanding production scope. Access
to Docker operations grants substantial authority on the host and belongs only
to the trusted local operator. The current deployment deliberately has no
public ingress, multi-user authorization or unattended remediation.

The [21 October candidate qualification](QUALIFICATION-2026-10-21.md) records
corrected Grafana, Qdrant and Tempo builds, exact validation and remaining image
findings. A successful scan is only one release condition. Historical
[20 October counts](QUALIFICATION-2026-10-20.md) and the
[26 September assessment](SECURITY-RELEASE-2026-09-26.md) remain available;
they do not describe this candidate. Remote or mutually untrusted use remains
outside the supported scope.


### Background sound and natural speech

AURA uses a local multilingual voice and a technical pronunciation lexicon, retaining
English pronunciations inside French replies. The operator name is Védric; French
replies use vous. The header's music control enables the original **Orbital Drift**
instrumental. Settings → Voice preferences adjusts its deliberately low level.
AURA speech takes priority; microphone recording mutes the music. Escape stops it.
An explicit browser gesture may be needed after reload. See [Voice](VOICE.md) for
qualification limits and [the audio notice](../apps/console/public/audio/NOTICE.md)
for the CC0 composition and separate voice licenses.

## Saved diagrams and reports

Select **Diagram** or **Report** beside the AURA conversation composer, or use an
explicit creation request in Auto mode. A document is published only after both
local generation and bounded consistency review complete. Their shared ceiling
is 180 seconds; this is not the short spoken-turn latency. Failure leaves the
request available for a deliberate retry and publishes no partial document.

Diagrams open at readable scale in a scrollable canvas. Use fullscreen, zoom,
Fit, or the horizontal/vertical presentation control for larger architectures.
The renderer measures and wraps text, separates groups and labels, and refuses
invalid layouts. Its 8-second worker deadline includes font readiness. Large
graphs stay scrollable instead of silently shrinking their labels. Motion
respects the same accessibility preference as the rest of the console.

SVG and PNG exports contain the complete diagram, legend and source references.
PNG has a 12-megapixel / 8,192-pixel-per-side bound; use SVG if that bound is
exceeded. JSON and Markdown use the authenticated saved document. Print / Save
PDF exports the selected report or complete diagram text outline, without the
rest of the conversation. Sources are references, not verification badges.

**Prepare memory note** opens an editable question in the memory form. Review the
scope, wording and source before saving; generation alone never writes Neo4j.
The [artifact contract and CLI guide](AURA-ARTIFACTS.md) describes limits,
provenance, retention, exports and failure behavior. Layout is performed locally
using [elkjs and its upstream license](../apps/console/public/notices/README.txt);
no diagram is sent to an external rendering service.
