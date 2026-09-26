# Private console and CLI

Ambicrafted provides one authenticated local control API for the graphical
console and the `./plateforme` CLI. It binds to **127.0.0.1:8787**, runs one
analysis at a time, and requires an explicit human decision before delivering
an actionable diagnosis. It does not execute proposed remediation commands.
This deployment supports one trusted workstation operator. Remote publication,
multiple tenants and high availability require a separate design.

## Install and start

Run from the checkout root, with the pinned Node/npm versions declared in
`apps/console/package.json` and `uv` available:

```sh
uv sync --locked --all-extras --project agents/sre-agent
uv sync --locked --project mcp-servers/runbooks
uv sync --locked --project apps/control-api
cd apps/console
npm ci
npm run build
cd ../..
./plateforme servir
```

The wrapper also finds `~/.local/bin/uv` when it is not on `PATH`. It resolves
the checkout from its own location, so it works from another current directory.
Do not move an installed checkout without reinstalling the user service.
The gateway, local inference service and knowledge index must be configured as
described in [operations](OPERATIONS.md). Starting the console does not silently
start Docker services or send confidential workloads to a remote model.

From a second terminal:

```sh
./plateforme ouvrir
./plateforme statut
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
failed, interrupted or budget-exhausted analysis (or invalid CLI arguments);
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

## Local voice through the CLI

The voice commands use the same authenticated API as the console:

```sh
./plateforme voix statut
printf '%s' 'Bonjour, la plateforme est disponible.' | ./plateforme voix parler --sortie /private/path/bonjour.wav
./plateforme voix transcrire /private/path/question.webm
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

The repository's `.mcp.json` declares `plateforme-controle` alongside the runbook
server. Start the authenticated local API before connecting this adapter:

```sh
uv run --locked --project apps/control-api python -m plateforme.mcp
```

The stdio tools are `plateforme_sante`, `plateforme_analyses` and
`plateforme_runbooks`. They read health, analysis metadata and the runbook
inventory through the same API. The private key is read internally; never put
it into an MCP configuration or command line. There is no approval, shell or
editing tool. Relative paths in `.mcp.json` require the repository root as the
client working directory.

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
