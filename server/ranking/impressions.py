"""
Writing the training signal: which posts a viewer was served, and what they did with them.

Impressions are only ever written for the posts actually returned in a feed
page, and only the viewer's own rows are updated by their engagement and by
their client's dwell reports.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import FeedImpression

logger = logging.getLogger(__name__)

ENGAGEMENT_WINDOW = timedelta(hours=24)
MAX_PER_REQUEST = 50
MAX_DWELL_MS = 10 * 60 * 1000


def enabled():
    return getattr(settings, 'RANKING_LOG_IMPRESSIONS', True)


def log_page(viewer, posts, *, first_position, variant, ranker, model_version='', features_by_id=None,
             served_at=None, synthetic=False):
    """Bulk-insert one row per served post (at most ``MAX_PER_REQUEST``). Never raises."""
    if not enabled() or not posts:
        return []
    served_at = served_at or timezone.now()
    features_by_id = features_by_id or {}
    rows = [
        FeedImpression(viewer_id=viewer.id, post_id=p.id, position=first_position + i, variant=variant,
                       ranker=ranker, model_version=model_version, served_at=served_at,
                       features=features_by_id.get(p.id), synthetic=synthetic)
        for i, p in enumerate(posts[:MAX_PER_REQUEST])
    ]
    try:
        return FeedImpression.objects.bulk_create(rows)
    except Exception:
        logger.warning('Could not log feed impressions', exc_info=True)
        return []


def log_served(viewer, served):
    """
    Log a ``posts.feed.Served`` page. Pages ranked by v2 already carry their
    feature vectors; for the others the same ``features.build`` runs after
    the response, as of the time served, in a Celery task.
    """
    rows = log_page(viewer, served.posts, first_position=served.first_position, variant=served.variant,
                    ranker=served.ranker, model_version=served.model_version, features_by_id=served.features)
    missing = [r.pk for r in rows if r.features is None and r.pk]
    if missing:
        from .tasks import fill_impression_features

        def dispatch():
            try:
                fill_impression_features.apply_async(args=[missing], queue='default')
            except Exception:
                logger.warning('Background dispatch failed', exc_info=True)
        transaction.on_commit(dispatch)
    return rows


def mark_engaged(user_id, post_id, when=None):
    """Flag the viewer's impressions of this post from the last 24 hours as engaged. One UPDATE."""
    when = when or timezone.now()
    try:
        return FeedImpression.objects.filter(
            viewer_id=user_id, post_id=post_id, engaged=False,
            served_at__gte=when - ENGAGEMENT_WINDOW, served_at__lte=when,
        ).update(engaged=True, engaged_at=when)
    except Exception:
        logger.warning('Could not record feed engagement', exc_info=True)
        return 0
