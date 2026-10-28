"""
Prometheus metrics for the feed ranker, on the registry django-prometheus serves at /metrics.

* ``ranking_feature_mean{feature}``: mean of each feature over the last
  window ranker v2 scored in this process (serving-time view of the inputs).
* ``ranking_feature_psi{feature}``: Population Stability Index of the last
  day's impressions against the model's training data. A Celery beat task
  computes it and leaves it in the shared cache, and a collector reads it at
  scrape time, so whichever web process is scraped reports the same value.
* ``ranking_v2_fallbacks_total{reason}``: times v2 handed a page back to v1.
"""
from django.core.cache import cache
from prometheus_client import REGISTRY, Counter, Gauge, Histogram
from prometheus_client.core import GaugeMetricFamily

PSI_CACHE_KEY = 'ranking:feature-psi'
PSI_CACHE_SECONDS = 3 * 24 * 3600

FEATURE_MEAN = Gauge('ranking_feature_mean', 'Mean of each ranking feature in the last scored window', ['feature'])
FALLBACKS = Counter('ranking_v2_fallbacks_total', 'Feed pages ranker v2 handed back to v1', ['reason'])
SCORE_SECONDS = Histogram('ranking_v2_score_seconds', 'Time to build features and score one candidate window',
                          buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5))


class PsiCollector:
    def collect(self):
        family = GaugeMetricFamily('ranking_feature_psi', 'Population Stability Index of each ranking feature, '
                                   'last day vs training data', labels=['feature'])
        try:
            data = cache.get(PSI_CACHE_KEY) or {}
        except Exception:
            data = {}
        for name, value in sorted(data.get('psi', {}).items()):
            family.add_metric([name], value)
        yield family

    def describe(self):
        return []  # values come from the cache at scrape time


_registered = False


def register_collectors():
    global _registered
    if not _registered:
        REGISTRY.register(PsiCollector())
        _registered = True
