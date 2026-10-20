# Evaluations

Node 22.23.3 and npm 11.10.0 are the validated toolchain. Install from the lock:

```sh
npm ci --ignore-scripts --no-fund
npm test
npm audit --audit-level=moderate
```

`npm test` validates the archived evaluation fixtures offline. It is not a model
run. The supported qualification runner uses the existing locked Python
environments for the real agent, control API and MCP server.

## Local-only model checks

Load the root environment through direnv, install the three locked Python
environments, then select an explicit retrieval mode and a new private output:

```sh
npm run eval:local -- --retrieval lexical \
  --runtime-revision YOUR_RECORDED_LOCAL_RUNTIME_DIGEST \
  --output /absolute/private/new-qualification-directory
```

The launcher forwards arguments to `qualify_agent.py run`, preserving its exit
code. Exit **2** means mechanical contracts passed but expert review remains
pending; it is not release acceptance. `CONFIDENTIAL_KEY` must already be loaded
and only the `local` alias is used. Semantic retrieval requires a disposable
Qdrant on an explicitly supplied nonproduction port; see the qualification guide.

See [the dated validation results](RESULTS-2026-09-26.md), including retrieval
false positives and the remaining triage limitations.

## Representative workflow qualification

The [69-case supervised qualification suite](qualification/README.md) runs the
real LangGraph workflow and NEXUS MCP tools against isolated synthetic sources.
It separates deterministic safety/provenance contracts from a mandatory expert
review. It also documents bounded HTTP/process lifecycle and long-duration
checks. None of these commands silently targets the workstation databases.

## Retired prompt-only comparison

The former four prompt-only local checks and one provider comparison are retained
under [archive/](archive/) as historical inputs. Promptfoo is no longer installed
or invoked by this project: its unused provider dependency tree still contained
known high/critical findings after upgrading to the latest release reviewed on
20 October 2026. Removing that tool removes the affected executable dependencies;
no advisory suppression or audit omission is used.

`eval:compare` is intentionally removed. The supported suite measures the real
local workflow; it does not claim a comparison against external providers or
an independent human quality assessment. Never send customer material to an
external evaluator. Historical September reports describe the toolchain used
then, not the current one.

Keep generated outputs outside Git. Record the configuration, model digests,
latency, failures and costs when comparing runs. Expand representative cases
before relying on an aggregate pass rate. Agent security contracts are tested
in the Python suites, including the human gate and provenance registry.
