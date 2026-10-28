"""
Ranking endpoints.

* ``POST /api/ranking/events/``: the feed reports what the viewer actually
  saw (dwell time) and opened, in batches. Only the caller's own impressions
  from the last 24 hours, of posts they can still see, are updated; anything
  else in the batch is ignored.
* ``GET /api/ranking/me/impressions/``: the caller's own recent impressions,
  with the features and ranker behind each one (a personal debug view).
* ``GET /api/ranking/metrics/``: staff-only aggregates per experiment arm.
"""
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from core import visibility

from . import features, model_store
from .impressions import ENGAGEMENT_WINDOW, MAX_DWELL_MS, MAX_PER_REQUEST
from .models import FeedImpression


class FeedEventsThrottle(UserRateThrottle):
    """The client sends a batch about every 10 seconds while the feed is open, plus one when it's hidden."""

    scope = 'feed_events'

    def get_rate(self):
        return getattr(settings, 'RANKING_EVENTS_THROTTLE', '30/min')


class EventSerializer(serializers.Serializer):
    post = serializers.IntegerField(min_value=1)
    dwell_ms = serializers.IntegerField(min_value=0, required=False)
    opened = serializers.BooleanField(required=False, default=False)


class EventsSerializer(serializers.Serializer):
    events = EventSerializer(many=True, allow_empty=False, max_length=MAX_PER_REQUEST)


class FeedEventsView(APIView):
    throttle_classes = [FeedEventsThrottle]

    def post(self, request):
        data = EventsSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = request.user
        now = timezone.now()
        by_post = {}
        for e in data.validated_data['events']:
            agg = by_post.setdefault(e['post'], {'dwell_ms': 0, 'opened': False})
            agg['dwell_ms'] = max(agg['dwell_ms'], min(e.get('dwell_ms') or 0, MAX_DWELL_MS))
            agg['opened'] = agg['opened'] or e['opened']

        # The latest impression of each post, among the caller's own, still in its window and still visible.
        rows = FeedImpression.objects.filter(
            viewer=user, post_id__in=by_post, served_at__gte=now - ENGAGEMENT_WINDOW,
            post__in=visibility.visible_posts(user).filter(id__in=by_post),
        ).order_by('post_id', '-served_at')
        latest = {}
        for imp in rows:
            latest.setdefault(imp.post_id, imp)
        for imp in latest.values():
            agg = by_post[imp.post_id]
            if agg['dwell_ms']:
                imp.dwell_ms = max(imp.dwell_ms or 0, agg['dwell_ms'])
            if agg['opened'] and not imp.engaged:
                imp.engaged, imp.engaged_at = True, now
        if latest:
            FeedImpression.objects.bulk_update(latest.values(), ['dwell_ms', 'engaged', 'engaged_at'])
        return Response({'accepted': len(latest)}, status=status.HTTP_202_ACCEPTED)


# Features derived from other people's relationships or activity (whose friends
# know whom, which friends reacted) stay out of the debug view; the ranker may
# use them, but showing the numbers could reveal what privacy settings hide.
REDACTED = {features.INDEX['mutual_friends'], features.INDEX['friend_engagements']}


def _redact(vec):
    if not isinstance(vec, list):
        return None
    return [None if i in REDACTED else v for i, v in enumerate(vec)]


class MyImpressionsView(APIView):
    """Your own last 100 feed impressions. Nobody else's rows are reachable from here."""

    def get(self, request):
        rows = FeedImpression.objects.filter(viewer=request.user).order_by('-served_at', 'position')[:100]
        return Response({
            'features': features.FEATURES,
            'results': [{
                'post': r.post_id, 'position': r.position, 'variant': r.variant, 'ranker': r.ranker,
                'model_version': r.model_version, 'served_at': r.served_at, 'engaged': r.engaged,
                'engaged_at': r.engaged_at, 'dwell_ms': r.dwell_ms, 'features': _redact(r.features),
            } for r in rows],
        })


class RankingMetricsView(APIView):
    """Aggregates only: impressions and engagement per experiment arm, plus the live model's offline metrics."""

    permission_classes = [IsAdminUser]

    def get(self, request):
        raw = request.query_params.get('days', '7')
        days = min(max(int(raw), 1), 90) if raw.isdigit() else 7
        since = timezone.now() - timedelta(days=days)
        arms = (FeedImpression.objects.filter(served_at__gte=since, synthetic=False).exclude(variant='')
                .values('variant', 'ranker')
                .annotate(impressions=Count('id'), engaged=Count('id', filter=Q(engaged=True)))
                .order_by('variant', 'ranker'))
        model = model_store.current()
        return Response({
            'days': days,
            'arms': [{**a, 'engagement_rate': a['engaged'] / a['impressions'] if a['impressions'] else None}
                     for a in arms],
            'model': {'version': model.version, 'trained_at': model.meta.get('trained_at'),
                      'synthetic': model.meta.get('synthetic'), 'metrics': model.meta.get('metrics')}
            if model else None,
        })
