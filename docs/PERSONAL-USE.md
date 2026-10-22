# Your first complete session

Use this walkthrough after the [installation](../README.md#install). It exercises
the real UI and CLI with synthetic information, then shows where the operator's
judgement is required. Run terminal commands from the repository root.

## Open and check the workspace

```sh
./plateforme prerequis
./plateforme preparation
./plateforme ouvrir
```

The browser opens the private application at `http://127.0.0.1:8787` using a
single-use login ticket. In **Settings → Console password**, set a password if
you want to enter directly from Welcome later. Keep the workstation private;
publishing the repository does not make this HTTP service suitable for public
ingress. A different machine needs its own installation and acceptance.

Read **Readiness** before submitting work. A missing required capability needs
investigation even if the homepage loads. Choose English or French in the top bar;
AURA's conversation language is separate. Input/output use the OS defaults.
Use **Check microphone & sound**, then explicitly start a spoken conversation.
Browser autoplay and microphone permissions still require your interaction.

## Make a diagram you can inspect

Open AURA and start a new conversation. Choose the diagram format or ask:

> Draw a diagram of this supplied system: a browser calls a control API over HTTPS; the API
> reads PostgreSQL. Show those three components and two directed connections.
> The database transport and backup arrangements are unknown: label them as
> questions, without inventing additional deployed components.

Inspect the result against those facts. Use fit/zoom or the expanded view; the
SVG retains the layout at any scale, while PNG size is bounded for readability.
Check the legend and source catalogue before sharing. For a report, choose
**Report** and request an observations/unknowns/next-checks structure in the same conversation. A refusal
or a failed review is visible; it is not a saved, accepted document.

Attach a synthetic CSV or a supported office document and explicitly select it
for the next turn. [Supported formats and bounds](CONVERSATIONS.md#supported-formats-and-explicit-limits)
describe extraction; arbitrary file formats, macros and embedded programs are
not executed. An extracted document is context, not trusted instructions.

Reopen the conversation from history and verify the saved result. If a request
loses its final response, inspect history before starting another operation.
If you deliberately resend the unchanged request in the same open conversation,
with the same language, format and selected sources, the UI reuses its operation
ID. This is not an automatic retry. Reloading the page or changing the request
can create a new operation; inspect saved history before repeating work.
For CLI callers, reuse the returned/provided `--operation-id` for that same
request; a new ID means new work. Logging out cancels pending browser exports.

## Investigate without changing a system

In **Missions**, choose a relevant preset and replace its example with observed
facts. A preset selects a brief; it does not create a different autonomous expert
or connect to a client environment. For a first run use synthetic observations,
for example: PostgreSQL reports too many clients, but current connection counts,
pool settings and recent changes are not yet available.

Watch the investigation, then inspect the proposal and sources. Ask:

- Does the conclusion follow from the observations, or merely resemble a runbook?
- Are the complete quoted paragraphs relevant, with prerequisites preserved?
- What measurements, approval and rollback evidence are still missing?
- Would applying this proposal be appropriate in the actual environment?

Refuse or cancel when the evidence is insufficient. Approval records your
decision and makes the diagnostic deliverable available; **it does not execute
the proposed actions**. Never pipe the result into a shell or deployment tool.
The [measured model results](QUALIFICATION-2026-10-22.md) explain why human review
remains essential even when the mechanical guards pass.

The CLI uses the same control plane. Supply confidential text through a private
file or stdin, never a process argument:

```sh
./plateforme analyses creer --titre 'Synthetic database investigation' \
  --fichier /absolute/private/synthetic-alert.txt --attendre
./plateforme analyses lister
./plateforme analyses voir ANALYSIS_ID
```

Create the UTF-8 input file yourself with mode `0600`. Replace `ANALYSIS_ID` with
the returned 32-character identifier. If its status is `en_attente_humain`
(**Needs approval**), deliberately refuse this first proposal:

```sh
./plateforme analyses refuser ANALYSIS_ID --attendre
```

An error or exhausted budget can end a run before that decision stage. Inspect
its status and available evidence; do not repeatedly resubmit it to obtain a
favorable answer. See [all analysis operations](CONSOLE.md#analyze-and-decide) before
using approval, cancellation or export.

## Keep only reviewed memory

AURA can prepare a memory draft from a document. Review it, select an explicit
scope and save it yourself. Prefer questions or qualified observations over
asserting an unverified diagnosis as a fact. Saved memory provides context; it
does not train the model or independently validate the remembered statement.
Use separate client environments where confidentiality requires isolation:
scope names within the personal workspace are not tenant authorization.

## Verify recovery and monitoring

Open Grafana at `http://127.0.0.1:3000`. Start with **Mission control**, then
**Reliability & budgets** and **Browser & conversation**. Follow a trace when
available and inspect its request outcome. Empty/no-data panels do not establish
zero errors. The seven-day objectives are provisional personal SLOs, not an SLA.
Grafana has its own sign-in, separate from the console session. See
[monitoring setup](MONITORING.md#installation); do not publish passwords
or screenshots containing real incident data.

Before relying on the workspace, run a [backup and isolated restore drill](RECOVERY.md).
An encrypted archive on this same workstation does not protect against losing
the workstation. Choose an independent destination and protect the recovery
identity separately, then prove you can recover from that destination.

The final personal acceptance tasks are practical: test your microphone and
speakers in both languages, review representative proposals for your work,
complete an off-host recovery and, if required, configure and receive a real
alert. Keep the [operating guide](OPERATIONS.md) for updates, restarts and rollback.
