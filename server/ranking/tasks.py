import logging
from datetime import timedelta

import numpy as np
from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from . import features, model_store, training
from .metrics import PSI_CACHE_KEY, PSI_CACHE_SECONDS
from .models import FeedImpression

logger = logging.getLogger(__name__)

PURGE_BATCH = 5000
PSI_SAMPLE = 50000


@shared_task(name='ranking.tasks.purge_old_impressions')
def purge_old_impressions():
    """Retention: impressions are personal data and are kept for 90 days (``RANKING_IMPRESSION_RETENTION_DAYS``)."""
    days = getattr(settings, 'RANKING_IMPRESSION_RETENTION_DAYS', 90)
    cutoff = timezone.now() - timedelta(days=days)
    total = 0
    while True:
        ids = list(FeedImpression.objects.filter(served_at__lt=cutoff).values_list('id', flat=True)[:PURGE_BATCH])
        if not ids:
            break
        total += FeedImpression.objects.filter(id__in=ids).delete()[0]
    if total:
        logger.info('Purged %d feed impressions older than %d days', total, days)
    return total


def fill_features(impressions):
    """Compute and store feature vectors for impressions logged without them, as of when each was served."""
    groups = {}
    for imp in impressions:
        groups.setdefault((imp.viewer_id, imp.served_at), []).append(imp)
    for (_, served_at), rows in groups.items():
        cands = [features.Candidate(r.post.id, r.post.author_id, r.post.group_id, r.post.page_id,
                                    r.post.created_at, r.post.post_type, r.post.shared_post_id) for r in rows]
        X = features.build(rows[0].viewer, cands, served_at)
        for r, vec in zip(rows, X.tolist(), strict=True):
            r.features = vec
    FeedImpression.objects.bulk_update(impressions, ['features'], batch_size=500)
    return len(impressions)


@shared_task(name='ranking.tasks.fill_impression_features')
def fill_impression_features(ids):
    rows = list(FeedImpression.objects.filter(id__in=ids[:500], features__isnull=True)
                .select_related('viewer', 'post'))
    return fill_features(rows) if rows else 0


@shared_task(name='ranking.tasks.compute_feature_psi')
def compute_feature_psi():
    """
    Drift: PSI of each feature over the last day's served impressions against
    the training split of the live model. Stored in the cache for the
    ``ranking_feature_psi`` gauge.
    """
    model_store.reset()  # a worker process may have an old model cached
    model = model_store.current()
    if model is None:
        return None
    reference = model.meta.get('training_distribution') or {}
    since = timezone.now() - timedelta(days=1)
    vectors = list(FeedImpression.objects.filter(served_at__gte=since, features__isnull=False,
                                                 synthetic=bool(model.meta.get('synthetic')))
                   .order_by('-served_at').values_list('features', flat=True)[:PSI_SAMPLE])
    width = len(features.FEATURES)
    X = np.asarray([v for v in vectors if isinstance(v, list) and len(v) == width], dtype=float).reshape(-1, width)
    if not len(X):
        return None
    out = {}
    for i, name in enumerate(features.FEATURES):
        ref = reference.get(name)
        if not ref:
            continue
        out[name] = round(training.psi(ref['expected'], training.distribution(X[:, i], ref['edges'])), 6)
    cache.set(PSI_CACHE_KEY, {'psi': out, 'model': model.version, 'rows': int(len(X)),
                              'computed_at': timezone.now().isoformat()}, PSI_CACHE_SECONDS)
    drifted = {k: v for k, v in out.items() if v > 0.2}
    if drifted:
        logger.warning('Ranking feature drift (PSI > 0.2): %s', drifted)
    return out
