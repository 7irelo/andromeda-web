"""
One way to notify someone: `notify(...)`.

It applies, in order:
- blocks (in either direction, nothing is delivered);
- the recipient's per-category preferences for in-app, email and push;
- grouping: repeats of the same event on the same thing ("Thandi and 12
  others liked your post") update one unread notification instead of
  stacking new ones;
- delivery: the per-user WebSocket, Web Push (when VAPID keys are
  configured and the user subscribed), and email (instant for the few
  categories that warrant it; everything else waits for the daily digest).
"""
import json
import logging
from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Notification, NotificationPreference, PushSubscription

logger = logging.getLogger(__name__)
GROUP_WINDOW = timedelta(hours=24)
MAX_ACTORS = 3

# Preference categories shown in settings, with defaults per channel.
CATEGORIES = {
    'likes': {'label': 'Reactions to your posts', 'in_app': True, 'push': False, 'email': False},
    'comments': {'label': 'Comments and replies', 'in_app': True, 'push': True, 'email': False},
    'mentions': {'label': 'Mentions', 'in_app': True, 'push': True, 'email': True},
    'friends': {'label': 'Friend requests', 'in_app': True, 'push': True, 'email': True},
    'messages': {'label': 'Messages', 'in_app': True, 'push': True, 'email': False},
    'groups': {'label': 'Groups and pages', 'in_app': True, 'push': False, 'email': False},
    'marketplace': {'label': 'Marketplace', 'in_app': True, 'push': True, 'email': False},
    'videos': {'label': 'New videos from channels you follow', 'in_app': True, 'push': False, 'email': False},
    # Safety notices (e.g. content removed) can't be turned off in-app.
    'account': {'label': 'Account and safety', 'in_app': True, 'push': True, 'email': True, 'locked': True},
}
_TYPE_CATEGORY = {
    Notification.TYPE_LIKE: 'likes', Notification.TYPE_COMMENT: 'comments', Notification.TYPE_MENTION: 'mentions',
    Notification.TYPE_FRIEND_REQUEST: 'friends', Notification.TYPE_FRIEND_ACCEPTED: 'friends',
    Notification.TYPE_FOLLOW: 'groups', Notification.TYPE_MESSAGE: 'messages',
    Notification.TYPE_GROUP_INVITE: 'groups', Notification.TYPE_POST_SHARE: 'likes',
}
_KIND_CATEGORY = {
    'price_drop': 'marketplace', 'listing_digest': 'marketplace', 'listing_message': 'marketplace',
    'new_video': 'videos', 'group_join_approved': 'groups', 'group_invite': 'groups', 'page_admin': 'groups',
}


def category_for(notification_type, extra):
    if notification_type == Notification.TYPE_SYSTEM:
        return _KIND_CATEGORY.get((extra or {}).get('kind'), 'account')
    return _TYPE_CATEGORY.get(notification_type, 'account')


def preferences(user):
    pref = NotificationPreference.objects.filter(user=user).first()
    stored = pref.channels if pref else {}
    out = {}
    for key, spec in CATEGORIES.items():
        row = {ch: bool(stored.get(key, {}).get(ch, spec[ch])) for ch in ('in_app', 'push', 'email')}
        if spec.get('locked'):
            row['in_app'] = True
        out[key] = row
    return out


def _blocked(a_id, b_id):
    if not a_id or not b_id:
        return False
    from users.models import Block
    from django.db.models import Q
    return Block.objects.filter(Q(blocker_id=a_id, blocked_id=b_id) | Q(blocker_id=b_id, blocked_id=a_id)).exists()


def _grouped_title(actors, others, verb):
    names = actors[:2]
    if others <= 0:
        lead = ' and '.join(names)
    elif others == 1 and len(names) == 1:
        lead = f'{names[0]} and 1 other'
    else:
        lead = f'{names[0]} and {others + len(names) - 1} others'
    return f'{lead} {verb}'


def notify(recipient, notification_type, title, *, sender=None, body='', extra=None, group_key='',
           group_verb='', push_url=''):
    """Create (or fold into) a notification and deliver it. Returns the Notification, or None if suppressed."""
    extra = dict(extra or {})
    recipient_id = getattr(recipient, 'id', recipient)
    sender_id = getattr(sender, 'id', sender)
    if sender_id and sender_id == recipient_id:
        return None
    if _blocked(recipient_id, sender_id):
        return None
    from django.contrib.auth import get_user_model
    user = recipient if hasattr(recipient, 'email') else get_user_model().objects.filter(pk=recipient_id).first()
    if user is None or not user.is_active:
        return None
    category = category_for(notification_type, extra)
    prefs = preferences(user)[category]
    if not prefs['in_app'] and not prefs['push'] and not prefs['email']:
        return None
    sender_obj = sender if hasattr(sender, 'username') or sender is None else \
        get_user_model().objects.filter(pk=sender_id).first()

    notif = None
    if group_key:
        with transaction.atomic():
            notif = (Notification.objects.select_for_update()
                     .filter(recipient=user, group_key=group_key, is_read=False,
                             updated_at__gte=timezone.now() - GROUP_WINDOW).first())
            if notif is not None:
                actors = notif.extra.get('actors', [])
                name = sender_obj.username if sender_obj else ''
                if name and name not in actors:
                    actors = [name] + actors
                count = notif.extra.get('count', 1) + 1
                notif.extra = {**notif.extra, **extra, 'actors': actors[:MAX_ACTORS], 'count': count}
                if group_verb:
                    notif.title = _grouped_title(actors, count - len(actors[:2]), group_verb)
                notif.sender = sender_obj
                notif.save(update_fields=['extra', 'title', 'sender', 'updated_at'])
    if notif is None:
        if sender_obj and group_key:
            extra.update({'actors': [sender_obj.username], 'count': 1})
        notif = Notification.objects.create(
            recipient=user, sender=sender_obj, notification_type=notification_type, title=title[:255],
            body=body, extra=extra, group_key=group_key[:120], in_app=prefs['in_app'],
        )

    payload = {'id': notif.id, 'type': notification_type, 'title': notif.title, 'body': notif.body[:200],
               'sender': sender_obj.username if sender_obj else None,
               'sender_avatar': sender_obj.avatar_url if sender_obj else None,
               'created_at': notif.created_at.isoformat(), **{k: v for k, v in extra.items() if k.endswith('_id')}}
    if prefs['in_app']:
        transaction.on_commit(lambda: push_websocket(user.id, payload))
    if prefs['push']:
        transaction.on_commit(lambda: send_push(user.id, notif.title, notif.body[:120], push_url))
    if prefs['email'] and category in ('mentions', 'friends', 'account'):
        transaction.on_commit(lambda: _email_now(notif.id))
    return notif


def push_websocket(user_id, payload):
    try:
        async_to_sync(get_channel_layer().group_send)(
            f'notifications_{user_id}', {'type': 'send_notification', **payload})
    except Exception:
        logger.warning('WS push failed for user %s', user_id, exc_info=True)


def push_enabled():
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def send_push(user_id, title, body, url=''):
    if not push_enabled():
        return
    from .tasks import deliver_web_push
    try:
        deliver_web_push.delay(user_id, title, body, url)
    except Exception:
        logger.warning('Background dispatch failed', exc_info=True)


def web_push_payload(title, body, url):
    # The shape Angular's service worker (SwPush) renders as a notification.
    return json.dumps({'notification': {
        'title': title, 'body': body, 'icon': '/assets/icons/icon-192x192.png',
        'data': {'onActionClick': {'default': {'operation': 'navigateLastFocusedOrOpen', 'url': url or '/notifications'}}},
    }})


def _email_now(notification_id):
    from .tasks import send_notification_email
    try:
        send_notification_email.delay(notification_id)
    except Exception:
        logger.warning('Background dispatch failed', exc_info=True)


__all__ = ['notify', 'preferences', 'category_for', 'CATEGORIES', 'PushSubscription']
