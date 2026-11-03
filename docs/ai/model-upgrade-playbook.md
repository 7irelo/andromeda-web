# Model-upgrade playbook

How to decide whether a new model replaces one in `ai/app/gateway.py`. Decide
per job: a model that wins for agents may be a poor deal for smart replies.

## 1. Check the basics

- Read the provider's migration notes for parameter changes and removed features.
- Confirm the price and update `PRICES`. An unknown model is costed at $0.
- Check data-retention terms if it comes from a new provider or tier.

## 2. Record a baseline

Run the suites for the affected jobs on the current model and keep the output.

| Job | Command | Bar |
|---|---|---|
| Moderation | `python -m evals.run_moderation --dataset moderation_holdout_v1.jsonl --gate 0.85` | Macro-F1 at or above the gate; **0 severe misses and 0 false removals** |
| Smart replies | `python -m evals.run_replies` | Safety gate passes; wins counted only when both judging orders agree |
| Assistant | `python -m evals.run_assistant` | No safety task fails; success rate and cost per task no worse |
| Retrieval | `python manage.py eval_retrieval` (in `server/`) | **0 visibility leaks**; recall@10 no worse |
| Rewrite cache, if the embedding model changes | `python -m evals.run_query_cache` | Re-pick the threshold: similarity scores shift between models |

Catch-up, listing drafts and Ask answers have no eval suite yet. A change to those
routes needs a manual review of real-shaped samples, and the review should say so.

## 3. Change one thing

Edit one job's route in a branch. Keep the old model as the fallback for now.
Don't change prompts in the same step, or you can't tell which caused a difference.

## 4. Compare

Rerun the same suites and compare quality, cost per item and p95 latency.

- **Any safety regression blocks the change**, whatever the savings.
- Sample sizes are small (24 held-out moderation items), so a one-item swing is
  noise. Read the changed items rather than trusting the headline number.
- Changing the embedding model means re-embedding everything with
  `manage.py reindex`, as vectors from different models can't be compared.

## 5. Roll out

1. Where a job supports it, A/B test with `core/experiments.bucket` and compare
   with `manage.py reply_metrics` or `ab_report`.
2. Watch `ai_cost_usd_total`, `ai_latency_seconds` and `ai_fallbacks_total`.
3. Remove the old route only after a stable period.

## 6. Roll back

Revert the route and redeploy the AI service. Routes hold no state, except for
embeddings, so keep the old vectors until the new index is proven.

## 7. Record it

Note the date, the job, the before and after numbers and the decision in the pull
request, and add a row below.

| Date | Job | Change | Result | Decision |
|---|---|---|---|---|
| | | | | |

No upgrade has been run through this playbook yet.
