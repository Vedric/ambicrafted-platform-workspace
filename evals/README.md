# Evaluations

Node 22.23.3 and npm 11.10.0 are the validated toolchain. Install from the lock:

```sh
npm ci --ignore-scripts --no-fund
npm test
npm audit --audit-level=moderate
```

`npm test` validates evaluation configuration offline. It is not a model run.

## Local-only model checks

Load the root environment through direnv and run:

```sh
PROMPTFOO_DISABLE_TELEMETRY=1 npm run eval:local -- --no-cache --no-write
```

Four synthetic cases check JSON output, abstention without documentation,
instruction injection and exact source passages. The provider uses
`CONFIDENTIAL_KEY`; assertions are deterministic JavaScript/JSON checks,
with no external LLM judge. These small checks do not establish production
incident quality, and do not test the agent orchestration itself.

See [the dated validation results](RESULTS-2026-09-26.md), including retrieval
false positives and the remaining triage limitations.

## Public-data comparison

`npm run eval:compare` uses `promptfooconfig.yaml`: one synthetic IAM-policy
case, local and external providers, and an external LLM judge. Its
`ORCHESTRATOR_KEY` must be restricted to the required aliases and budgeted.
Never add customer logs, code, configuration, identifiers or real incident
text to this configuration. External evaluation is an explicit separate command.

Keep generated outputs outside Git. Record the configuration, model digests,
latency, failures and costs when comparing runs. Expand representative cases
before relying on an aggregate pass rate. Agent security contracts are tested
in the Python suites, including the human gate and provenance registry.
