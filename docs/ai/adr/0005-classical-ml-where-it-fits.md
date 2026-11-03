# ADR 0005: Not using an LLM where something simpler does the job

- Status: accepted
- Date: 2026-11-03
- Scope: `server/ranking/`, `ai/distill/`, `ai/app/features/query_cache.py`

## Decision

- **Feed ranking uses LightGBM.** It scores many posts per request, so per-call
  LLM cost and latency don't fit. On synthetic engagement it reached AUC 0.705
  against 0.629 for the heuristic. That says nothing about real users yet.
- **Search rewrite and rerank stay off by default.** On the retrieval eval they
  moved recall@10 from 0.968 to 0.979 but p50 latency from 0.38 s to 4.1 s, which
  isn't worth it for a search box.
- **Moderation's distilled classifier ships off.** It costs about $0.001 per
  1,000 items against about $0.8, but let one borderline item through on each
  test set, missing its own bar. See [`ai/README.md`](../../../ai/README.md).
- **The rewrite cache uses a strict threshold.** At 0.94 similarity it had no
  false hits on 20 near-miss pairs but hit only 27% of same-intent pairs. Lower
  thresholds saved more calls and started returning results for the wrong city
  or product. The threshold was chosen on these same 35 pairs, so treat it as a
  starting point and watch `ai_query_cache_total`.

## Consequences

Each of these can be turned on when new measurements justify it. A cheaper option
that failed its bar stays in the repository with its numbers.
