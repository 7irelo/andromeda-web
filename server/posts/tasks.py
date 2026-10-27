"""
Post side effects: link previews, hashtags and @mentions.
"""
import logging
import re

from celery import shared_task

logger = logging.getLogger(__name__)

HASHTAG_RE = re.compile(r'(?<![\w#])#(\w{2,50})')
MENTION_RE = re.compile(r'(?<![\w@])@([\w.@+-]{2,150})')
URL_RE = re.compile(r'https?://[^\s<>"\']{4,2000}')
MAX_TAGS = 20
MAX_MENTIONS = 20


def extract_tags(text):
    return list(dict.fromkeys(t.lower() for t in HASHTAG_RE.findall(text or '')))[:MAX_TAGS]


def extract_mentions(text):
    return list(dict.fromkeys(MENTION_RE.findall(text or '')))[:MAX_MENTIONS]


def first_url(text):
    m = URL_RE.search(text or '')
    return m.group(0).rstrip('.,);!?') if m else ''


def process_post(post, created):
    """Sync hashtags and queue mention notifications/link preview after a save."""
    from django.db import transaction
    from .models import PostTag

    tags = extract_tags(post.content)
    PostTag.objects.filter(post=post).exclude(name__in=tags).delete()
    PostTag.objects.bulk_create([PostTag(post=post, name=t) for t in tags], ignore_conflicts=True)

    from moderation.tasks import queue_moderation
    if created or post.content:
        queue_moderation('post', post.id)

    mentions = extract_mentions(post.content)
    if mentions:
        transaction.on_commit(lambda: send_mention_notifications.delay(post.id, mentions, created))
    if (post.link_url or first_url(post.content)) and not post.link_title:
        transaction.on_commit(lambda: fetch_link_preview.delay(post.id))


@shared_task(name='posts.tasks.fetch_link_preview', queue='default',
             autoretry_for=(OSError,), retry_backoff=True, max_retries=2)
def fetch_link_preview(post_id):
    from .link_preview import UnsafeURL, fetch_preview
    from .models import Post

    post = Post.objects.filter(pk=post_id).first()
    if post is None:
        return
    url = post.link_url or first_url(post.content)
    if not url:
        return
    try:
        preview = fetch_preview(url)
    except UnsafeURL as exc:
        logger.info('Link preview refused for post %s: %s', post_id, exc)
        return
    except Exception:
        logger.warning('Link preview failed for post %s', post_id, exc_info=True)
        return
    # Third-party images are not stored: loading them in viewers' browsers
    # would leak IPs to arbitrary hosts (and CSP only allows our own images).
    Post.objects.filter(pk=post_id).update(
        link_url=url[:200], link_title=preview['title'], link_description=preview['description'],
        post_type=Post.TYPE_LINK if post.post_type == Post.TYPE_TEXT else post.post_type,
    )


@shared_task(name='posts.tasks.send_mention_notifications', queue='notifications')
def send_mention_notifications(post_id, usernames, created=True):
    from django.contrib.auth import get_user_model

    from core import visibility
    from notifications.models import Notification
    from notifications.tasks import _push_to_websocket
    from .models import Post

    post = Post.objects.select_related('author').filter(pk=post_id).first()
    if post is None:
        return
    already = set(Notification.objects.filter(
        notification_type=Notification.TYPE_MENTION, extra__post_id=post_id
    ).values_list('recipient_id', flat=True)) if not created else set()
    for user in get_user_model().objects.filter(username__in=usernames, is_active=True).exclude(id=post.author_id):
        # Only notify people who can actually see the post.
        if user.id in already or not visibility.can_view_post(user, post):
            continue
        notif = Notification.objects.create(
            recipient=user, sender=post.author, notification_type=Notification.TYPE_MENTION,
            title=f'{post.author.username} mentioned you in a post', extra={'post_id': post_id},
        )
        _push_to_websocket(user.id, {
            'id': notif.id, 'type': 'mention', 'title': notif.title,
            'sender': post.author.username, 'post_id': post_id,
            'created_at': notif.created_at.isoformat(),
        })
