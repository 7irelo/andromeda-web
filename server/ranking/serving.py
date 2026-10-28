"""
Ranker v2: LightGBM P(engage) over the candidate window, behind the
``feed_ranker`` experiment.

The candidates are the same visibility-filtered window ranking v1 uses
(``posts.feed``); v2 only reorders them. Any failure (no model yet, a model
trained on other features, an exception while scoring) returns ``None`` and
the caller serves v1 instead.
"""
import logging
from dataclasses import asdict, dataclass, field
from datetime import timedelta

import numpy as np
from django.conf import settings
from django.core.cache import cache

from core import experiments

from . import features, model_store
from .metrics import FALLBACKS, FEATURE_MEAN, SCORE_SECONDS

logger = logging.getLogger(__name__)

EXPERIMENT = 'feed_ranker'
MAX_RUN = 2               # at most this many posts in a row by one author
WINDOW_CACHE_SECONDS = 30 * 60
OFTEN = 3
OFTEN_MESSAGES = 5
POPULAR = 10
FRIENDS_FOR_POPULAR = 2   # never say "popular with your friends" about a single friend's like
SIMILAR = 0.3
ENGAGING_AUTHOR = 0.2


def assigned_variant(user):
    """The user's sticky arm of the ``feed_ranker`` experiment; 'v1' for everyone when v2 is switched off."""
    if not getattr(settings, 'RANKING_V2_ENABLED', True):
        return 'v1'
    weights = getattr(settings, 'RANKING_FEED_RANKER_WEIGHTS', {'v1': 50, 'v2': 50})
    return experiments.bucket(user.id, EXPERIMENT, weights)


@dataclass
class Ranked:
    ids: list[int]
    features: dict[int, list[float]] = field(default_factory=dict)
    probability: dict[int, float] = field(default_factory=dict)
    # Features pushing each post up, strongest first (positive contributions only).
    drivers: dict[int, list[str]] = field(default_factory=dict)
    model_version: str = ''


def diversify(items, author_of, max_run=MAX_RUN):
    """
    Keep the score order, except that no author appears more than ``max_run``
    times in a row: the best-scored post by someone else moves up instead.
    """
    queue, out = list(items), []
    while queue:
        tail = out[-max_run:]
        blocked = author_of(tail[0]) if len(tail) == max_run and len({author_of(x) for x in tail}) == 1 else None
        i = next((k for k, x in enumerate(queue) if author_of(x) != blocked), 0)
        out.append(queue.pop(i))
    return out


def score(viewer, candidates, as_of, model=None):
    """Rank ``candidates`` with the current model. Returns a ``Ranked`` or ``None`` (caller falls back to v1)."""
    model = model or model_store.current()
    if model is None:
        FALLBACKS.labels('no_model').inc()
        return None
    try:
        with SCORE_SECONDS.time():
            X = features.build(viewer, candidates, as_of)
            p, contrib = model.predict(X)
    except Exception:
        logger.exception('Ranker v2 failed to score; serving v1')
        FALLBACKS.labels('error').inc()
        return None
    candidates = candidates[:len(X)]
    if len(X):
        for i, name in enumerate(features.FEATURES):
            FEATURE_MEAN.labels(name).set(float(X[:, i].mean()))
    order = sorted(range(len(candidates)), key=lambda i: (-p[i], -candidates[i].id))
    order = diversify(order, lambda i: candidates[i].author_id)
    names = features.FEATURES
    drivers = {}
    for i, c in enumerate(candidates):
        row = contrib[i, :len(names)]
        drivers[c.id] = [names[j] for j in np.argsort(-row) if row[j] > 0][:6]
    return Ranked(
        ids=[candidates[i].id for i in order],
        features={c.id: X[i].tolist() for i, c in enumerate(candidates)},
        probability={c.id: float(p[i]) for i, c in enumerate(candidates)},
        drivers=drivers,
        model_version=model.version,
    )


def ranked_window(viewer, candidates, anchor):
    """
    ``score`` for a feed window, cached per (viewer, anchor, model) so the
    following pages of the same session reuse it instead of re-scoring.
    """
    model = model_store.current()
    if model is None:
        FALLBACKS.labels('no_model').inc()
        return None
    key = f'ranking:v2:{viewer.id}:{anchor.isoformat()}:{model.version}'
    try:
        hit = cache.get(key)
    except Exception:
        hit = None
    if hit:
        return Ranked(ids=hit['ids'], features={int(k): v for k, v in hit['features'].items()},
                      probability={int(k): v for k, v in hit['probability'].items()},
                      drivers={int(k): v for k, v in hit['drivers'].items()}, model_version=hit['model_version'])
    ranked = score(viewer, candidates, anchor, model=model)
    if ranked is not None:
        try:
            cache.set(key, asdict(ranked), WINDOW_CACHE_SECONDS)
        except Exception:
            logger.warning('Could not cache the ranked window', exc_info=True)
    return ranked


# ── "Why am I seeing this?" ──────────────────────────────────────────────────

def _name(user):
    return user.first_name or user.username


def _sentence(feature, post, f, now):
    """The explanation for one driving feature, or None if it wouldn't be true or would say too much."""
    name = _name(post.author)
    value = f[features.INDEX[feature]]
    count = features.raw_count(value)
    if feature == 'is_own_post':
        return 'Your post'
    if feature == 'author_likes_30d' and count >= OFTEN:
        return f"Because you often like {name}'s posts"
    if feature == 'author_comments_30d' and count >= OFTEN:
        return f"Because you often comment on {name}'s posts"
    if feature == 'author_messages_30d' and count >= OFTEN_MESSAGES:
        return f'Because you and {name} message each other'
    if feature == 'friend_engagements' and count >= FRIENDS_FOR_POPULAR:
        return 'Popular with your friends'
    if feature == 'interest_similarity' and value >= SIMILAR:
        return "Similar to posts you've engaged with"
    if feature == 'in_member_group' and value and post.group_id:
        return f'From {post.group.name}, a group you’re in'
    if feature == 'follows_page' and value and post.page_id:
        return f'From {post.page.name}, a Page you follow'
    if feature == 'is_friend' and value:
        return f'From your friend {name}'
    if feature == 'shared_groups' and count >= 1:
        return f'From {name}, who’s in groups with you'
    if feature in ('engagement_velocity', 'post_likes', 'post_comments'):
        total = features.raw_count(f[features.INDEX['post_likes']]) + \
            features.raw_count(f[features.INDEX['post_comments']])
        if total >= POPULAR:
            return 'Popular right now'
    if feature == 'age_hours' and now - post.created_at < timedelta(hours=24):
        return f'New from {name}'
    if feature == 'author_engagement_rate' and value >= ENGAGING_AUTHOR:
        return f'People often engage with {name}’s posts'
    # mutual_friends has no sentence: naming it could reveal friendships hidden by privacy settings.
    return None


def _context(post, f):
    """Fallback when no driver has a true sentence: where the post comes from."""
    if f[features.INDEX['is_own_post']]:
        return 'Your post'
    if f[features.INDEX['follows_page']] and post.page_id:
        return f'From {post.page.name}, a Page you follow'
    if f[features.INDEX['is_friend']]:
        return f'From your friend {_name(post.author)}'
    if f[features.INDEX['in_member_group']] and post.group_id:
        return f'From {post.group.name}, a group you’re in'
    return 'Recent post'


def reason(post, f, drivers, now):
    """Human explanation from the strongest feature that has a true, safe sentence."""
    for feature in drivers:
        text = _sentence(feature, post, f, now)
        if text:
            return text
    return _context(post, f)
