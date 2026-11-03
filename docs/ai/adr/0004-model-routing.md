# ADR 0004: Per-job model routes across providers

- Status: accepted
- Date: 2026-11-03
- Scope: `ai/app/gateway.py`

## Context

Jobs differ a lot: a smart reply must be cheap and fast, while an agent plan
needs the strongest reasoning. Any single provider can also have an outage.

## Decision

Every job has an ordered list of routes in `gateway.ROUTES`, and features name
the job, never a model. Anthropic is primary for reasoning, agents, grounded
answers and vision. OpenAI provides embeddings, the free moderation screen and
fallbacks. Deepgram handles speech.

A transient failure moves to the next route, and a per-provider circuit breaker
skips a failing one. A refusal is final: it isn't retried on another provider,
so a fallback can't be used to get around a safety decision.

## Consequences

- A job can be re-pointed by editing one table, then checked with its eval (see
  the [model-upgrade playbook](../model-upgrade-playbook.md)).
- Fallback output can differ in quality, and a fallback model isn't evaluated by
  default.
- Cross-provider failover has been unit-tested with fake providers, but there
  is no recorded live failover drill.
