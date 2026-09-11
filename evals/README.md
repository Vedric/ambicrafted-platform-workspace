# promptfoo evaluations

Compares the local model (`local`) against the frontier (`balanced`) on real
SRE tasks, with an LLM judge for the `llm-rubric` assertions.

## Running

```sh
cd ~/platform/workspace/evals
npx promptfoo eval          # runs promptfooconfig.yaml
npx promptfoo view          # results UI
```

Nothing to export. All three providers (`local`, `balanced`, and the judge)
read from the environment:

| Variable | Origin | Role |
|---|---|---|
| `ORCHESTRATOR_KEY` | workspace `.env`, loaded by direnv | LiteLLM virtual key, through `apiKeyEnvar` |
| `LITELLM_BASE_URL` | same | gateway URL, through `apiBaseUrl: "{{ env.LITELLM_BASE_URL }}"` |

`OPENAI_API_KEY` and `OPENAI_BASE_URL` are neither read nor needed; if they
happen to be in the shell, these providers ignore them. Verified on
2026-08-27 with both variables explicitly removed from the environment
(`env -u`).

## Why `ORCHESTRATOR_KEY` and not the master key

Least privilege (ADR 0007, lessons from the rotation):

- the master key grants every right on the gateway (key creation, unlimited
  spend, administration); the harness only needs to call aliases;
- `ORCHESTRATOR_KEY` is a virtual key, hashed in the database: rotating the
  master key does not invalidate it. There is therefore **nothing left to
  propagate** here when the master key is rotated;
- its own rotation happens in the workspace `.env`, never in this directory.

Confidential cases (client data) do not go through this harness: they would
use `CONFIDENTIAL_KEY` and the `local` alias only (rule 2 of CLAUDE.md).

## Checking the key without displaying it

```sh
echo "len=${#ORCHESTRATOR_KEY} prefix=${ORCHESTRATOR_KEY:0:12}"
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer $ORCHESTRATOR_KEY" "$LITELLM_BASE_URL/models"   # expect 200
```

## Structure

- `promptfooconfig.yaml`: providers, judge, latency threshold, list of cases;
- `cas/*.yaml`: one file per task, with its assertions;
- `.promptfoo/` and `output/` are ignored by git.

## Assertions: three traps already paid for

The comments in `cas/01-iam-policy.yaml` record failures that were diagnosed
the hard way. They are worth reading before adding a case, because each one
produced a result that looked like a model verdict and was not.

**A `regex` assertion is compiled with `new RegExp(value)` and no flags.** An
inline `(?i)` is rejected by V8 (`Invalid group`), so the assertion errored
for *every* model regardless of content. Case-insensitivity is therefore
written out with character classes, and accents are handled either by cutting
before the accented vowel (`privil`, `personnalis`) or by listing the
variants (`r[oô]le`).

**A `not-contains-any` was wrong in both directions at once.** Written
without accents, `"aucun probleme"` never matched a correctly accented
`"aucun problème"`, a dead guard. And the bare substring `"conforme"` fired
on `"n'est pas conforme"`, so it failed a *good* answer. Rewritten as a
`not-regex`, tolerant of accents and immunised against negation with a
lookbehind.

**Default `max_tokens` was 1024**, and both models were ending at
`finish_reason="length"`, cut mid-sentence. The judge then failed them for a
point that was absent because it was truncated, not because it was
unaddressed. Raised to 4096: we measure the answer, not the truncation.

There is also a provider-specific one: Qwen3 has reflection mode on by
default, which consumes the whole token budget and leaves `content` empty;
promptfoo then displays the `reasoning_content` prefixed with `Thinking:`.
`passthrough: { think: false }` disables it; `passthrough` is the only
channel promptfoo offers for a parameter outside the OpenAI spec.

The general shape of all four is the same, and it is the same lesson as
everywhere else in this repository: **an assertion that has never been
observed failing on a bad answer, and passing on a good one, is not an
assertion.** Test both directions.
