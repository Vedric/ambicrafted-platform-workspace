# ADR 0001: LiteLLM as the single gateway

Status: accepted, in local production since 2026-08-24
Date: 2026-08-24

## Context
Four subscriptions (human seats, not integrable) and an envelope of Anthropic
API credits. We need a single point for routing, cost tracking and the
compartmentalisation of mission data (banking / energy / defence clients).

## Decision
LiteLLM in Compose (with Postgres), OpenAI-compatible endpoint on
127.0.0.1:4000. Semantic aliases (smart/balanced/fast/local/local-embed).
Virtual keys per consumer, including "confidential-only" restricted to
local + local-embed. No fallback out of "local".
Compose subnet fixed at 172.28.0.0/24 (chosen outside the ranges already in
use, verified with ip route).

## Alternatives rejected
- Direct per-provider calls: no cost view, compartmentalisation by declaration
  only, changing model is intrusive.
- OpenRouter: does not integrate the local model, one more intermediary on
  the data.

## Consequences
+ Changing model = one line of YAML
+ Compartmentalisation verified by a negative test on 08-24:
  "key not allowed to access model" on a local -> smart attempt
+ Spend traceable per key in Postgres
- One more service to operate (accepted on a workstation)
- Model costs must be declared in model_info for accurate tracking
