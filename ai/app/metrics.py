from prometheus_client import Counter, Histogram

REQUESTS = Counter('ai_requests_total', 'Model calls', ['job', 'provider', 'model', 'outcome'])
TOKENS = Counter('ai_tokens_total', 'Tokens processed', ['job', 'model', 'kind'])
COST = Counter('ai_cost_usd_total', 'Estimated spend in USD', ['job', 'model'])
LATENCY = Histogram('ai_latency_seconds', 'Model call latency', ['job', 'model'],
                    buckets=(0.25, 0.5, 1, 2, 4, 8, 16, 32))
FALLBACKS = Counter('ai_fallbacks_total', 'Calls served by a fallback route', ['job'])
BUDGET_REJECTIONS = Counter('ai_budget_rejections_total', 'Requests refused by the per-user budget', ['job'])
DECISIONS = Counter('ai_moderation_decisions_total', 'Moderation outcomes', ['decision'])
ATTRIBUTION = Counter('ai_citations_total', 'Citations checked against the source set', ['valid'])
INJECTION_DROPS = Counter('ai_injection_sources_dropped_total', 'Retrieved sources dropped as prompt-injection attempts')
