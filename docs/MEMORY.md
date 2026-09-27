# Dedicated graph memory

The local implementation passed a real browser/API/Neo4j note–link–conversation
round trip. Consult the [delivery report](RELEASE-0.4.0.md) and security inventory. This is a private, single-operator feature.

The platform owns a separate Neo4j database. Existing customer databases on the same
machine are never selected automatically. Its HTTP port is **127.0.0.1:47474**; Bolt
listens only inside its container. A generated password stays in the repository's
private `.env`. Do not print this file, inspect container environments or pass the
password in command arguments.

```sh
./plateforme memoire installer
./plateforme memoire statut
./plateforme memoire lister --scope personal
```

The installer starts only `gateway/neo4j-memory.yml`, initializes the unique note ID
constraint and scope index, and verifies an authenticated query. It preserves an
existing password. If port 47474 is occupied, resolve that conflict explicitly; do
not redirect the API to a customer database. Volumes use the separate
`ambicrafted-memory` Compose project.

In **Knowledge → Memory graph**, choose a scope such as `personal` or `internal-sre`.
Add an observation, decision, open question or preference, and record its source.
Connect related notes within that scope. **Use this context with AURA** creates a
conversation containing a dated copy of the selected note. Review the selected
attachment before sending a question. Linked notes are not copied automatically.

Scopes organize one operator's notes. They are not tenant permissions. Use separate
platform instances and storage for separate customers. Notes are untrusted context,
not verified diagnostic evidence; ATLAS continues to ground diagnoses in runbooks.
Never store credentials in notes. Deleting a note removes its graph relationships,
but previously copied conversation attachments and backups have separate retention.

To create a note from the CLI, prepare an operator-owned file in mode `0600` with
`scope`, `titre`, `contenu`, `source`, and optionally `type` (`fact`, `decision`,
`question`, `preference`), then:

```sh
./plateforme memoire creer --fichier /path/to/private-note.json
./plateforme memoire voir NOTE_UUID --scope personal
./plateforme memoire lier FIRST_UUID SECOND_UUID --scope personal
./plateforme memoire supprimer NOTE_UUID --scope personal
```

Read-only MCP clients use NEXUS tools `controle__plateforme_memoire` and
`controle__plateforme_note_memoire`. Both require an explicit scope. No arbitrary
Cypher, remote database URL or write tool is accepted through MCP. The browser and
CLI use the same authenticated control API for mutations.

Limits: 5,000 notes globally, 4,000 characters of content per note, 100 search results
and at most 30 relationships per note. Narrow the search to find older notes.

The platform backup now includes `memoire.json` when the dedicated memory password
is configured. A failed configured-memory export fails the backup rather than
silently omitting notes. The file is owner-only, bounded, checksummed and inventoried
in the manifest. Restore testing starts a separate authenticated Neo4j container,
loads validated notes and same-scope relationships using parameterized queries, and
compares all restored content before removing the container. It never imports into
the running database. A synthetic two-note/one-link restore passed on 2026-09-27.

The export uses a logical read-committed transaction, not a transactionally consistent
snapshot across Neo4j, SQLite, PostgreSQL and Qdrant. Stop mutations during a continuity
backup. Labels outside `AmbicraftedNote`, database users and custom plugins are not
part of this logical export; this service does not expose them as platform features.
An intentional production restore requires the operator's continuity procedure,
validated backup and maintenance window. [Operations](OPERATIONS.md) describes the
shared backup and disposable restoration commands.
