"""
Features for (viewer, post) pairs, computed in batch for a candidate window.

One code path serves both training and serving: the feed calls ``build`` when
it ranks or logs a page and stores the resulting vector on each impression,
and ``train_ranker`` learns from those stored vectors. Everything is computed
**as of** a timestamp (the page's anchor) from rows created before it, so a
feature never sees engagement that happened after the post was shown.

The whole batch costs a fixed number of queries, however many candidates
there are (up to ``MAX_CANDIDATES``): every query is grouped by author or by
post, never issued per post.

Each feature depends only on the viewer, the post and the time, never on
which other posts are in the batch, so a page scored inside a 500-post
window and the same page logged on its own get identical vectors.
"""
import logging
import math
from dataclasses import dataclass
from datetime import timedelta

import numpy as np
from django.conf import settings
from django.db import connection
from django.db.models import Count, Q

from core import visibility

logger = logging.getLogger(__name__)

FEATURE_VERSION = 1
FEATURES = [
    'is_own_post',            # 1 if the viewer wrote it
    'is_friend',              # 1 if the author is a friend
    'author_likes_30d',       # log1p(viewer's likes on the author's posts, last 30 days)
    'author_comments_30d',    # log1p(viewer's comments on the author's posts, last 30 days)
    'author_messages_30d',    # log1p(DMs exchanged with the author, last 30 days)
    'shared_groups',          # log1p(groups both belong to)
    'mutual_friends',         # log1p(mutual friends): Neo4j, or SQL when the graph is off
    'in_member_group',        # 1 if posted in a group the viewer belongs to
    'follows_page',           # 1 if posted by a Page the viewer follows
    'age_hours',              # log1p(hours since posting)
    'post_likes',             # log1p(likes so far)
    'post_comments',          # log1p(comments so far)
    'engagement_velocity',    # log1p((likes + comments) per hour since posting)
    'friend_engagements',     # log1p(likes + comments on it by the viewer's friends)
    'media_type',             # categorical, see MEDIA_TYPES
    'interest_similarity',    # cosine(post embedding, viewer's interest vector); 0 if unavailable
    'author_engagement_rate',  # smoothed share of the author's feed impressions that were engaged with
]
CATEGORICAL = ['media_type']
MEDIA_TYPES = {'text': 0, 'image': 1, 'video': 2, 'link': 3, 'share': 4}
INDEX = {name: i for i, name in enumerate(FEATURES)}

MAX_CANDIDATES = 500
WINDOW_DAYS = 30
INTEREST_POSTS = 100      # most recent engagements of each kind that form the interest vector
RATE_PRIOR = 0.1          # smoothing for author_engagement_rate: a new author starts at 10%...
RATE_PRIOR_WEIGHT = 10    # ...worth ten impressions


@dataclass(frozen=True)
class Candidate:
    id: int
    author_id: int
    group_id: int | None
    page_id: int | None
    created_at: object
    post_type: str
    shared_post_id: int | None = None


# Columns to ``values_list`` from a Post queryset, in ``Candidate`` order.
CANDIDATE_FIELDS = ('id', 'author_id', 'group_id', 'page_id', 'created_at', 'post_type', 'shared_post_id')


def candidates_from(qs):
    return [Candidate(*row) for row in qs.values_list(*CANDIDATE_FIELDS)]


def _grouped(qs, key, agg=None):
    agg = agg or Count('id')
    return {row[key]: row['n'] for row in qs.values(key).annotate(n=agg)}


def _messages(viewer, author_ids, since, as_of):
    """Messages exchanged (either direction) in DMs between the viewer and each author. Three queries."""
    from chats.models import ChatMember, Message

    if not author_ids:
        return {}
    my_dms = ChatMember.objects.filter(user=viewer, room__room_type='direct').values('room_id')
    other = dict(ChatMember.objects.filter(room_id__in=my_dms, user_id__in=author_ids)
                 .values_list('room_id', 'user_id'))
    if not other:
        return {}
    counts = {}
    rows = (Message.objects.filter(room_id__in=other.keys(), created_at__gte=since, created_at__lt=as_of,
                                   is_deleted=False)
            .values('room_id').annotate(n=Count('id')))
    for row in rows:
        uid = other[row['room_id']]
        counts[uid] = counts.get(uid, 0) + row['n']
    return counts


def mutual_friends(viewer, author_ids, friends):
    """Mutual-friend counts per author. Neo4j when it's enabled (falling back on error), SQL otherwise."""
    if not author_ids:
        return {}
    if getattr(settings, 'NEO4J_ENABLED', False):
        try:
            from neomodel import db
            rows, _ = db.cypher_query(
                'MATCH (v:UserNode {user_id: $viewer})-[:FRIEND_WITH]-(m:UserNode)-[:FRIEND_WITH]-(a:UserNode) '
                'WHERE a.user_id IN $authors AND m.user_id <> a.user_id '
                'RETURN a.user_id, count(DISTINCT m)',
                {'viewer': viewer.id, 'authors': list(author_ids)},
            )
            return {int(a): int(n) for a, n in rows}
        except Exception:
            logger.warning('Mutual friends from Neo4j failed; using SQL', exc_info=True)
    from users.models import FriendRequest

    if not friends:
        return {}
    rows = FriendRequest.objects.filter(
        Q(sender_id__in=author_ids, receiver_id__in=friends) | Q(receiver_id__in=author_ids, sender_id__in=friends),
        status=FriendRequest.STATUS_ACCEPTED,
    ).values_list('sender_id', 'receiver_id')
    counts = {}
    for s, r in rows:
        for author, other in ((s, r), (r, s)):
            if author in author_ids and other in friends and other != author:
                counts[author] = counts.get(author, 0) + 1
    return counts


def _engaged_post_ids(viewer, since, as_of):
    """Posts the viewer recently liked, commented on or saved: the basis of their interest vector."""
    from posts.models import Comment, Like, SavedPost

    window = dict(created_at__gte=since, created_at__lt=as_of)
    ids = set()
    for qs in (Like.objects.filter(user=viewer, **window), Comment.objects.filter(author=viewer, **window),
               SavedPost.objects.filter(user=viewer, **window)):
        ids.update(qs.order_by('-created_at').values_list('post_id', flat=True)[:INTEREST_POSTS])
    return list(ids)


_SIMILARITY_SQL = (
    'WITH interest AS ('
    "  SELECT AVG(vector) AS v FROM retrieval_embedding WHERE kind = 'posts' AND chunk_ix = 0"
    '  AND object_id = ANY(%s)'
    ') '
    'SELECT e.object_id, 1 - (e.vector <=> interest.v) FROM retrieval_embedding e, interest '
    "WHERE interest.v IS NOT NULL AND e.kind = 'posts' AND e.chunk_ix = 0 AND e.object_id = ANY(%s)"
)


def interest_similarity(viewer, post_ids, since, as_of):
    """
    Cosine between each post's embedding and the mean embedding of posts the
    viewer engaged with recently. Missing embeddings, an empty history, a
    viewer who opted out of AI features, or no pgvector all give 0.
    """
    if getattr(viewer, 'ai_opt_out', False) or not post_ids:
        return {}
    try:
        engaged = _engaged_post_ids(viewer, since, as_of)
        if not engaged:
            return {}
        if connection.vendor == 'postgresql':
            # Both the mean and the distances stay inside Postgres: 500 floats come back, not 500 vectors.
            with connection.cursor() as cur:
                cur.execute(_SIMILARITY_SQL, [engaged, list(post_ids)])
                return {int(oid): float(sim) for oid, sim in cur.fetchall() if sim is not None}
        from retrieval.models import Embedding

        rows = Embedding.objects.filter(kind='posts', chunk_ix=0, object_id__in=set(engaged) | set(post_ids))
        vectors = {oid: np.asarray(vec, dtype=float) for oid, vec in rows.values_list('object_id', 'vector')}
        history = [vectors[i] for i in engaged if i in vectors]
        if not history:
            return {}
        interest = np.mean(history, axis=0)
        norm = np.linalg.norm(interest)
        if not norm:
            return {}
        out = {}
        for pid in post_ids:
            v = vectors.get(pid)
            if v is not None and np.linalg.norm(v):
                out[pid] = float(v @ interest / (np.linalg.norm(v) * norm))
        return out
    except Exception:
        logger.warning('Interest similarity unavailable', exc_info=True)
        return {}


def _author_rates(author_ids, since, as_of):
    from .models import FeedImpression

    if not author_ids:
        return {}
    rows = (FeedImpression.objects.filter(post__author_id__in=author_ids, served_at__gte=since, served_at__lt=as_of)
            .values('post__author_id').annotate(n=Count('id'), k=Count('id', filter=Q(engaged=True))))
    return {r['post__author_id']: (r['k'] or 0, r['n']) for r in rows}


def media_type(c):
    if c.shared_post_id:
        return MEDIA_TYPES['share']
    return MEDIA_TYPES.get(c.post_type, 0)


def build(viewer, candidates, as_of):
    """
    Feature matrix for ``candidates`` (a list of ``Candidate``), one row per
    candidate in the same order, shape ``(len(candidates), len(FEATURES))``.
    """
    from groups.models import GroupMember
    from pages.models import PageFollow
    from posts.models import Comment, Like

    candidates = list(candidates)[:MAX_CANDIDATES]
    X = np.zeros((len(candidates), len(FEATURES)), dtype=float)
    if not candidates:
        return X
    since = as_of - timedelta(days=WINDOW_DAYS)
    post_ids = [c.id for c in candidates]
    author_ids = {c.author_id for c in candidates} - {viewer.id}
    window = dict(created_at__gte=since, created_at__lt=as_of)

    friends = visibility.friend_ids(viewer)
    groups = set(GroupMember.objects.filter(user=viewer).values_list('group_id', flat=True))
    pages = set(PageFollow.objects.filter(user=viewer).values_list('page_id', flat=True))
    likes = _grouped(Like.objects.filter(user=viewer, post__author_id__in=author_ids, **window), 'post__author_id')
    comments = _grouped(Comment.objects.filter(author=viewer, post__author_id__in=author_ids, **window),
                        'post__author_id')
    messages = _messages(viewer, author_ids, since, as_of)
    shared = _grouped(GroupMember.objects.filter(user_id__in=author_ids, group_id__in=groups), 'user_id') \
        if groups else {}
    mutual = mutual_friends(viewer, author_ids, friends)
    post_likes = _grouped(Like.objects.filter(post_id__in=post_ids, created_at__lt=as_of), 'post_id')
    post_comments = _grouped(Comment.objects.filter(post_id__in=post_ids, created_at__lt=as_of), 'post_id')
    friend_likes = _grouped(Like.objects.filter(post_id__in=post_ids, user_id__in=friends, created_at__lt=as_of),
                            'post_id') if friends else {}
    friend_comments = _grouped(Comment.objects.filter(post_id__in=post_ids, author_id__in=friends,
                                                      created_at__lt=as_of), 'post_id') if friends else {}
    similarity = interest_similarity(viewer, post_ids, since, as_of)
    rates = _author_rates({c.author_id for c in candidates}, since, as_of)

    log1p = math.log1p
    for row, c in enumerate(candidates):
        own = c.author_id == viewer.id
        hours = max(0.0, (as_of - c.created_at).total_seconds() / 3600)
        n_likes, n_comments = post_likes.get(c.id, 0), post_comments.get(c.id, 0)
        k, n = rates.get(c.author_id, (0, 0))
        X[row] = (
            float(own),
            float(c.author_id in friends),
            0.0 if own else log1p(likes.get(c.author_id, 0)),
            0.0 if own else log1p(comments.get(c.author_id, 0)),
            0.0 if own else log1p(messages.get(c.author_id, 0)),
            0.0 if own else log1p(shared.get(c.author_id, 0)),
            0.0 if own else log1p(mutual.get(c.author_id, 0)),
            float(bool(c.group_id) and c.group_id in groups),
            float(bool(c.page_id) and c.page_id in pages),
            log1p(hours),
            log1p(n_likes),
            log1p(n_comments),
            log1p((n_likes + n_comments) / max(hours, 1.0)),
            log1p(friend_likes.get(c.id, 0) + friend_comments.get(c.id, 0)),
            float(media_type(c)),
            similarity.get(c.id, 0.0),
            (k + RATE_PRIOR * RATE_PRIOR_WEIGHT) / (n + RATE_PRIOR_WEIGHT),
        )
    return X


def raw_count(value):
    """Undo the log1p of a count feature."""
    return int(round(math.expm1(value)))


def heuristic_score(X):
    """
    Ranking v1 (``posts.feed``) recomputed from feature vectors:
    recency x affinity x engagement. The training report uses it as the
    baseline on exactly the same impressions the model is scored on.
    """
    from posts import feed as v1

    X = np.atleast_2d(np.asarray(X, dtype=float))
    f = {name: X[:, i] for name, i in INDEX.items()}
    affinity = (1.0 + f['is_friend'] + 0.6 * f['author_likes_30d'] + 0.8 * f['author_comments_30d']
                + 0.4 * f['author_messages_30d'] + 0.5 * f['in_member_group'] + 0.3 * f['follows_page'])
    affinity = np.where(f['is_own_post'] > 0, 1.5, affinity)
    hours = np.expm1(f['age_hours'])
    recency = 0.5 ** (hours / v1.HALF_LIFE_HOURS)
    engagement = 1.0 + 0.35 * f['post_likes'] + 0.5 * f['post_comments']
    return recency * affinity * engagement
