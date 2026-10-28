"""
Nightly Postgres -> Neo4j reconciliation.

The outbox makes the projection reliable, not perfect: writes that bypass
signals (``QuerySet.update``, raw SQL, restores), events dead-lettered during a
long outage, or a graph rebuilt from an old dump all leave drift. This walks
users, accepted friendships, posts and likes in id ranges of
``GRAPH_RECONCILE_BATCH`` and compares each range with the graph, so memory
stays flat however large the tables grow. Missing nodes and edges are
created, extra ones deleted. Postgres is always the source of truth.

Drift per kind is added to ``GraphDrift`` and exported as
``graph_drift_total{kind}``.
"""
import logging

from django.conf import settings
from django.db.models import F, Max
from django.db.models.functions import Greatest, Least
from django.utils import timezone

from .models import GraphDrift

logger = logging.getLogger(__name__)

KINDS = ('user', 'friendship', 'post', 'like')


def _ranges(upper, batch):
    lo = 0
    while lo <= upper:
        yield lo, lo + batch
        lo += batch


def _users(graph, batch, repair):
    from users.models import User

    drift = 0
    upper = max(User.objects.aggregate(m=Max('id'))['m'] or 0, graph.max_ids()[0])
    for lo, hi in _ranges(upper, batch):
        rows = {r['id']: r for r in User.objects.filter(id__gte=lo, id__lt=hi)
                .values('id', 'username', 'first_name', 'last_name', 'is_verified')}
        in_graph = graph.user_ids(lo, hi)
        missing = rows.keys() - in_graph
        extra = in_graph - rows.keys()
        drift += len(missing) + len(extra)
        if repair:
            graph.upsert_users([{
                'user_id': r['id'], 'username': r['username'],
                'display_name': f"{r['first_name']} {r['last_name']}".strip() or r['username'],
                'is_verified': r['is_verified'],
            } for uid, r in rows.items() if uid in missing])
            graph.delete_users(sorted(extra))
    return drift


def _friendships(graph, batch, repair):
    from users.models import FriendRequest, User

    drift = 0
    accepted = FriendRequest.objects.filter(status=FriendRequest.STATUS_ACCEPTED).annotate(
        low=Least(F('sender_id'), F('receiver_id')), high=Greatest(F('sender_id'), F('receiver_id')))
    upper = max(User.objects.aggregate(m=Max('id'))['m'] or 0, graph.max_ids()[0])
    for lo, hi in _ranges(upper, batch):
        expected = set(accepted.filter(low__gte=lo, low__lt=hi).values_list('low', 'high'))
        actual = graph.friend_pairs(lo, hi)
        missing, extra = expected - actual, actual - expected
        drift += len(missing) + len(extra)
        if repair:
            graph.link_friends(sorted(missing))
            graph.unlink_friends(sorted(extra))
    return drift


def _posts(graph, batch, repair):
    from posts.models import Post

    drift = 0
    upper = max(Post.objects.aggregate(m=Max('id'))['m'] or 0, graph.max_ids()[1])
    for lo, hi in _ranges(upper, batch):
        rows = dict(Post.objects.filter(id__gte=lo, id__lt=hi).values_list('id', 'author_id'))
        in_graph = graph.post_ids(lo, hi)
        missing = rows.keys() - in_graph
        extra = in_graph - rows.keys()
        drift += len(missing) + len(extra)
        if repair:
            graph.upsert_posts([{'post_id': pid, 'author_id': rows[pid]} for pid in sorted(missing)])
            graph.delete_posts(sorted(extra))
    return drift


def _likes(graph, batch, repair):
    from posts.models import Like, Post

    drift = 0
    upper = max(Post.objects.aggregate(m=Max('id'))['m'] or 0, graph.max_ids()[1])
    for lo, hi in _ranges(upper, batch):
        expected = set(Like.objects.filter(post_id__gte=lo, post_id__lt=hi).values_list('user_id', 'post_id'))
        actual = graph.like_pairs(lo, hi)
        missing, extra = expected - actual, actual - expected
        drift += len(missing) + len(extra)
        if repair:
            graph.link_likes(sorted(missing))
            graph.unlink_likes(sorted(extra))
    return drift


CHECKS = {'user': _users, 'friendship': _friendships, 'post': _posts, 'like': _likes}


def reconcile(graph=None, batch=None, repair=True):
    """Compare (and by default repair) every kind. Returns ``{kind: drift}``."""
    if graph is None:
        from .graph import get_graph
        graph = get_graph()
    batch = batch or getattr(settings, 'GRAPH_RECONCILE_BATCH', 1000)
    now = timezone.now()
    result = {}
    # Nodes before edges, so repaired edges have both ends.
    for kind in KINDS:
        result[kind] = CHECKS[kind](graph, batch, repair)
        GraphDrift.objects.get_or_create(kind=kind)
        GraphDrift.objects.filter(kind=kind).update(total=F('total') + result[kind], last_run=result[kind],
                                                    checked_at=now)
        if result[kind]:
            logger.warning('Graph drift: %s %s item(s) %s', result[kind], kind, 'repaired' if repair else 'found')
    return result
