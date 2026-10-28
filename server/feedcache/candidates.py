"""
Home-feed candidate ids from Redis: hybrid fan-out.

* Fan-out on write: when a post commits, its id is pushed to the inboxes of
  the people whose feed draws from it (the author, their friends, members of
  its group, followers of its Page), as long as that audience is at most
  ``FEEDCACHE_FANOUT_THRESHOLD``.
* Fan-out on read: posts from bigger sources (authors with more friends than
  the threshold, large Pages and groups) are not pushed; ``candidates()``
  pulls them in when the feed is read.

The cache is an accelerator, never an authority. ``candidates()`` returns ids
only, and callers must still pass them through ``core.visibility`` (the feed
does this via ``feed_queryset``), so a stale or poisoned inbox can only ever
narrow or reorder what the viewer may already see, never widen it::

    from feedcache.candidates import candidates
    ids = candidates(user, CANDIDATE_WINDOW)
    qs = feed_queryset(user) if ids is None else feed_queryset(user).filter(id__in=ids)

``None`` means "no cache available": use the database query as before.
"""
import logging

from django.conf import settings
from django.db.models import Q

from .store import get_store

logger = logging.getLogger(__name__)

# Sources between PULL_RATIO x threshold and the threshold are both pushed and
# pulled, so a count wobbling around the threshold can't drop posts.
PULL_RATIO = 0.8


def enabled():
    return getattr(settings, 'FEEDCACHE_ENABLED', False)


def threshold():
    return settings.FEEDCACHE_FANOUT_THRESHOLD


def _pull_floor():
    return int(threshold() * PULL_RATIO)


# ── Read path ────────────────────────────────────────────────────────────────

def _pulled(user, limit):
    """Recent posts from large sources the viewer follows (fan-out on read)."""
    from core import visibility
    from django.contrib.auth import get_user_model
    from groups.models import Group
    from pages.models import Page, PageFollow
    from posts.models import Post

    floor = _pull_floor()
    pages = Page.objects.filter(id__in=PageFollow.objects.filter(user=user).values('page_id'),
                                followers_count__gt=floor).values('id')
    groups = Group.objects.filter(id__in=visibility.member_group_ids(user), members_count__gt=floor).values('id')
    friends = visibility.friend_ids(user)
    big_authors = get_user_model().objects.filter(id__in=friends, friends_count__gt=floor).values('id')
    sources = Q(page_id__in=pages) | Q(group_id__in=groups) | Q(author_id__in=big_authors)
    return list(Post.objects.filter(sources).order_by('-id').values_list('id', flat=True)[:limit])


def _source_ids(user, limit):
    """Everything the feed draws from, newest first: used to (re)build a cold inbox."""
    from posts.feed import feed_queryset

    return list(feed_queryset(user).order_by('-id').values_list('id', flat=True)[:limit])


def warm(user):
    """Build ``user``'s inbox from the database, then top up anything that committed meanwhile."""
    store = get_store()
    ids = _source_ids(user, settings.FEEDCACHE_MAX_ITEMS)
    store.build(user.id, ids)
    # A post that committed after the query above but whose fan-out ran before
    # the inbox existed would be missing; LPUSHX after the build closes the gap.
    newest = ids[0] if ids else 0
    from posts.feed import feed_queryset
    for post_id in reversed(list(feed_queryset(user).filter(id__gt=newest).order_by('-id')
                                 .values_list('id', flat=True)[:settings.FEEDCACHE_MAX_ITEMS])):
        store.push([user.id], post_id)
    return ids


def candidates(user, limit=None):
    """Up to ``limit`` candidate post ids, newest first, or None when the cache is off or unavailable."""
    if not enabled() or not getattr(user, 'is_authenticated', False):
        return None
    limit = limit or settings.FEEDCACHE_MAX_ITEMS
    try:
        store = get_store()
        inbox = store.read(user.id, limit)
        if inbox is None:
            warm(user)
            inbox = store.read(user.id, limit) or []
        merged = set(inbox) | set(_pulled(user, limit))
    except Exception:
        logger.warning('Feed cache unavailable; falling back to the database', exc_info=True)
        return None
    return sorted(merged, reverse=True)[:limit]


# ── Write path ───────────────────────────────────────────────────────────────

def audience(post, ignore_privacy=False):
    """Inboxes a post is pushed to on write. Over-inclusion is harmless (reads re-check visibility)."""
    from core import visibility
    from django.contrib.auth import get_user_model
    from groups.models import Group, GroupMember
    from pages.models import Page, PageFollow
    from posts.models import Post

    ids = {post.author_id}
    if not ignore_privacy and (post.privacy == Post.PRIVACY_PRIVATE or post.moderation_status == 'removed'):
        return ids
    limit = threshold()
    author = get_user_model().objects.filter(pk=post.author_id).first()
    if author is None:
        return ids
    if author.friends_count <= limit:
        ids |= visibility.friend_ids(author)
    if post.group_id and Group.objects.filter(pk=post.group_id, members_count__lte=limit).exists():
        ids |= set(GroupMember.objects.filter(group_id=post.group_id).values_list('user_id', flat=True))
    if post.page_id and Page.objects.filter(pk=post.page_id, followers_count__lte=limit).exists():
        ids |= set(PageFollow.objects.filter(page_id=post.page_id).values_list('user_id', flat=True))
    return ids - visibility.blocked_ids(author)


def fan_out(post):
    get_store().push(sorted(audience(post)), post.id)


def retract(post):
    """Take a post out of every inbox it could have been pushed to."""
    get_store().remove(sorted(audience(post, ignore_privacy=True)), post.id)


def invalidate(*user_ids):
    """Drop inboxes; they rebuild from the database on the next read."""
    get_store().drop([uid for uid in user_ids if uid])
