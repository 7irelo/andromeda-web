"""
The home feed: who it draws from, how it is ranked and how it pages.

Candidates are posts the viewer can see (``core.visibility``) from themselves,
their friends, groups they belong to and pages they follow, minus posts they
hid. Two orderings are offered:

* ``latest``: chronological, keyset-paginated on ``(created_at, id)``.
* ``top`` (default): ranking v1, a heuristic over the newest
  ``CANDIDATE_WINDOW`` candidates: recency decay x affinity x engagement.
  Once the window is exhausted the feed continues chronologically.
  Viewers in the ``v2`` arm of the ``feed_ranker`` experiment get the same
  window ordered by a LightGBM model instead (``ranking.serving``), with v1
  as the fallback.

Every page served is logged as impressions (``ranking.impressions``), the
training signal for the model.

Both are stable under new inserts: ``top`` pins the window to the time of the
first page and ``latest`` pages below the last row it returned. Cursors are
opaque to the client but carry nothing secret; every page is re-filtered
through the visibility service, so a forged cursor can only reorder what the
viewer may already see.
"""
import base64
import binascii
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from core import visibility
from .models import Comment, HiddenPost, Like

PAGE_SIZE = 20
CANDIDATE_WINDOW = 500
HALF_LIFE_HOURS = 36
INTERACTION_DAYS = 30
OFTEN = 3            # interactions in INTERACTION_DAYS that count as "often"
OFTEN_MESSAGES = 5
POPULAR = 10         # likes + comments for "Popular in <group>"
MAX_POSITION = 100_000

SORT_TOP = 'top'
SORT_LATEST = 'latest'


def feed_queryset(user):
    from pages.models import PageFollow

    friends = visibility.friend_ids(user)
    sources = (
        Q(author=user)
        | Q(author_id__in=friends)
        | Q(group_id__in=visibility.member_group_ids(user))
        | Q(page_id__in=PageFollow.objects.filter(user=user).values('page_id'))
    )
    hidden = HiddenPost.objects.filter(user=user).values('post_id')
    return visibility.visible_posts(user).filter(sources).exclude(id__in=hidden)


# ── Cursors ──────────────────────────────────────────────────────────────────

def encode_cursor(data):
    raw = json.dumps(data, separators=(',', ':')).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def decode_cursor(token):
    if not token:
        return {}
    if len(token) > 200:
        raise ValidationError({'cursor': 'Invalid cursor.'})
    try:
        data = json.loads(base64.urlsafe_b64decode(token + '=' * (-len(token) % 4)))
        if not isinstance(data, dict):
            raise ValueError
        out = {}
        if 't' in data:
            out['t'] = _parse_dt(data['t'])
        if 'c' in data:
            out['c'] = _parse_dt(data['c'])
            out['i'] = int(data['i'])
        if 'o' in data:
            out['o'] = int(data['o'])
            if not 0 <= out['o'] <= CANDIDATE_WINDOW:
                raise ValueError
        if 'p' in data:  # feed position of the next row, for the impression log only
            out['p'] = int(data['p'])
            if not 0 <= out['p'] <= MAX_POSITION:
                raise ValueError
        return out
    except (ValueError, TypeError, KeyError, binascii.Error, json.JSONDecodeError):
        raise ValidationError({'cursor': 'Invalid cursor.'})


def _parse_dt(value):
    dt = datetime.fromisoformat(str(value))
    if timezone.is_naive(dt):
        raise ValueError
    return dt


def _below(created_at, post_id):
    """Rows strictly after (created_at, id) in ``-created_at, -id`` order."""
    return Q(created_at__lt=created_at) | Q(created_at=created_at, id__lt=post_id)


# ── Signals for ranking and "Why am I seeing this?" ──────────────────────────

class Signals:
    """Everything the ranker and the reasons need about the viewer, fetched in a few grouped queries."""

    def __init__(self, user, author_ids, now):
        from pages.models import PageFollow

        self.user = user
        self.now = now
        author_ids = set(author_ids) - {user.id}
        since = now - timedelta(days=INTERACTION_DAYS)
        self.friends = visibility.friend_ids(user)
        self.groups = set(visibility.member_group_ids(user).values_list('group_id', flat=True))
        self.pages = set(PageFollow.objects.filter(user=user).values_list('page_id', flat=True))
        self.likes = self._counts(
            Like.objects.filter(user=user, created_at__gte=since, post__author_id__in=author_ids),
            'post__author_id')
        self.comments = self._counts(
            Comment.objects.filter(author=user, created_at__gte=since, post__author_id__in=author_ids),
            'post__author_id')
        self.messages = self._direct_messages(user, author_ids, since)

    @staticmethod
    def _counts(qs, key):
        return {row[key]: row['n'] for row in qs.values(key).annotate(n=Count('id'))}

    @staticmethod
    def _direct_messages(user, author_ids, since):
        """Messages exchanged (either direction) in DMs between the viewer and each author."""
        from chats.models import ChatMember, Message

        if not author_ids:
            return {}
        my_dms = ChatMember.objects.filter(user=user, room__room_type='direct').values('room_id')
        other = dict(ChatMember.objects.filter(room_id__in=my_dms, user_id__in=author_ids)
                     .values_list('room_id', 'user_id'))
        if not other:
            return {}
        counts = {}
        rows = (Message.objects.filter(room_id__in=other.keys(), created_at__gte=since, is_deleted=False)
                .values('room_id').annotate(n=Count('id')))
        for row in rows:
            uid = other[row['room_id']]
            counts[uid] = counts.get(uid, 0) + row['n']
        return counts

    def affinity(self, author_id, group_id, page_id):
        if author_id == self.user.id:
            return 1.5
        score = 1.0
        if author_id in self.friends:
            score += 1.0
        score += 0.6 * math.log1p(self.likes.get(author_id, 0))
        score += 0.8 * math.log1p(self.comments.get(author_id, 0))
        score += 0.4 * math.log1p(self.messages.get(author_id, 0))
        if group_id and group_id in self.groups:
            score += 0.5
        if page_id and page_id in self.pages:
            score += 0.3
        return score

    def reason(self, post):
        """A short, human explanation. Names only things the viewer can already see on the post."""
        author = post.author
        name = author.first_name or author.username
        if author.id == self.user.id:
            return 'Your post'
        if self.likes.get(author.id, 0) >= OFTEN:
            return f"Because you often like {name}'s posts"
        if self.comments.get(author.id, 0) >= OFTEN:
            return f"Because you often comment on {name}'s posts"
        if self.messages.get(author.id, 0) >= OFTEN_MESSAGES:
            return f'Because you and {name} message each other'
        in_my_group = post.group_id and post.group_id in self.groups
        if in_my_group and post.likes_count + post.comments_count >= POPULAR:
            return f'Popular in {post.group.name}'
        if post.page_id and post.page_id in self.pages:
            return f'From {post.page.name}, a Page you follow'
        if author.id in self.friends:
            if self.now - post.created_at < timedelta(hours=24):
                return 'New from a friend'
            return f'From your friend {name}'
        if in_my_group:
            return f'From {post.group.name}, a group you’re in'
        return 'Recent post'


def engagement(likes, comments):
    return 1.0 + 0.35 * math.log1p(likes) + 0.5 * math.log1p(comments)


def recency(created_at, now):
    age_hours = max(0.0, (now - created_at).total_seconds() / 3600)
    return 0.5 ** (age_hours / HALF_LIFE_HOURS)


# ── Pages ────────────────────────────────────────────────────────────────────

@dataclass
class Served:
    """One page of the feed, plus what the impression log needs to know about how it was made."""

    posts: list
    next_cursor: str | None
    reasons: dict
    first_position: int = 0
    variant: str = ''
    ranker: str = 'latest'
    model_version: str = ''
    features: dict = field(default_factory=dict)


def _load(qs, ids):
    """Fetch full rows for ``ids`` and return them in that order."""
    by_id = {p.id: p for p in qs.filter(id__in=ids)}
    return [by_id[i] for i in ids if i in by_id]


def _reasons(signals, posts):
    return {p.id: signals.reason(p) for p in posts}


def latest_page(user, full_qs, cursor, variant=''):
    qs = feed_queryset(user)
    if 'c' in cursor:
        qs = qs.filter(_below(cursor['c'], cursor['i']))
    rows = list(qs.order_by('-created_at', '-id').values_list('id', 'created_at')[:PAGE_SIZE + 1])
    more = len(rows) > PAGE_SIZE
    rows = rows[:PAGE_SIZE]
    posts = _load(full_qs, [r[0] for r in rows])
    position = cursor.get('p', 0)
    nxt = encode_cursor({'c': rows[-1][1].isoformat(), 'i': rows[-1][0], 'p': position + len(rows)}) \
        if more and rows else None
    signals = Signals(user, {p.author_id for p in posts}, timezone.now())
    return Served(posts, nxt, _reasons(signals, posts), first_position=position, variant=variant)


# Columns of a candidate row: v1 reads the first seven, ranking.features.Candidate the ones it names.
WINDOW_FIELDS = ('id', 'author_id', 'group_id', 'page_id', 'created_at', 'likes_count', 'comments_count',
                 'post_type', 'shared_post_id')


def candidate_window(user, anchor):
    """The newest ``CANDIDATE_WINDOW`` posts the viewer may see, as of ``anchor``. Both rankers start here."""
    return list(
        feed_queryset(user).filter(created_at__lte=anchor).order_by('-created_at', '-id')
        .values_list(*WINDOW_FIELDS)[:CANDIDATE_WINDOW]
    )


def rank_v1(user, rows, anchor):
    """Ranking v1: recency decay x affinity x engagement. Returns the rows in order and the signals behind them."""
    signals = Signals(user, {r[1] for r in rows}, anchor)
    scored = sorted(
        rows,
        key=lambda r: (recency(r[4], anchor) * signals.affinity(r[1], r[2], r[3]) * engagement(r[5], r[6]), r[0]),
        reverse=True,
    )
    return scored, signals


def as_candidates(rows):
    from ranking.features import Candidate

    return [Candidate(r[0], r[1], r[2], r[3], r[4], r[7], r[8]) for r in rows]


def top_page(user, full_qs, cursor):
    """
    The ranked window pinned at the first page's timestamp, then a
    chronological tail. Ranker v1 or v2 by the viewer's ``feed_ranker``
    experiment arm; v2 falls back to v1 whenever it can't score.
    """
    from ranking import serving

    variant = serving.assigned_variant(user)
    if 'c' in cursor:  # past the ranked window
        return latest_page(user, full_qs, cursor, variant=variant)

    anchor = cursor.get('t') or timezone.now()
    offset = cursor.get('o', 0)
    rows = candidate_window(user, anchor)
    ranked = serving.ranked_window(user, as_candidates(rows), anchor) if variant == 'v2' and rows else None
    if ranked is not None:
        order = ranked.ids
    else:
        scored, signals = rank_v1(user, rows, anchor)
        order = [r[0] for r in scored]

    page_ids = order[offset:offset + PAGE_SIZE]
    if offset + PAGE_SIZE < len(order):
        nxt = encode_cursor({'t': anchor.isoformat(), 'o': offset + PAGE_SIZE})
    elif len(rows) == CANDIDATE_WINDOW:
        oldest = rows[-1]
        nxt = encode_cursor({'c': oldest[4].isoformat(), 'i': oldest[0], 'p': len(rows)})
    else:
        nxt = None
    posts = _load(full_qs, page_ids)
    if ranked is None:
        return Served(posts, nxt, _reasons(signals, posts), first_position=offset, variant=variant, ranker='v1')
    reasons = {p.id: serving.reason(p, ranked.features[p.id], ranked.drivers.get(p.id, []), anchor) for p in posts}
    return Served(posts, nxt, reasons, first_position=offset, variant=variant, ranker='v2',
                  model_version=ranked.model_version, features={p.id: ranked.features[p.id] for p in posts})


def feed_page(user, full_qs, sort, cursor_token):
    """Returns ``(posts, next_cursor, reasons)`` for one page of the feed, and logs what was served."""
    from ranking import impressions

    cursor = decode_cursor(cursor_token)
    served = latest_page(user, full_qs, cursor) if sort == SORT_LATEST else top_page(user, full_qs, cursor)
    impressions.log_served(user, served)
    return served.posts, served.next_cursor, served.reasons
