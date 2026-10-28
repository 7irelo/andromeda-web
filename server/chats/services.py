"""
Chat actions shared by the REST views and the WebSocket consumer.

Both transports call the same functions, so the authorization rules (member
of the room, author of the message, allowed to message the other person in a
DM) are written once. Everything here is synchronous; the consumer wraps it
in ``database_sync_to_async``.
"""
import json
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from core import visibility
from .models import ChatMember, ChatRoom, Message, MessageReaction, MessageRead
from .serializers import MessageSerializer, reaction_summary

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 5000
PRESENCE_TTL_SECONDS = 6 * 3600


class ChatActionError(Exception):
    def __init__(self, code, detail, status=403):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


def group_name(room_id):
    return f'chat_{room_id}'


def is_member(room_id, user):
    return ChatMember.objects.filter(room_id=room_id, user=user).exists()


def can_send(room, user):
    """Members can post, except in a DM with someone who no longer accepts their messages."""
    if room.room_type != ChatRoom.TYPE_DIRECT:
        return True
    other = room.members.exclude(id=user.id).first()
    return other is None or visibility.can_message(user, other)


def message_queryset():
    return Message.objects.select_related('sender', 'reply_to__sender').prefetch_related('reactions')


def payload(msg):
    """JSON-safe serialization for channel-layer events (no viewer-specific fields)."""
    return json.loads(json.dumps(MessageSerializer(msg).data))


def broadcast(room_id, event):
    """Send an event to everyone connected to the room. Never fails the caller."""
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(group_name(room_id), event)
    except Exception:
        logger.warning('Chat broadcast failed', exc_info=True)


def broadcast_on_commit(room_id, event):
    transaction.on_commit(lambda: broadcast(room_id, event))


def _own_message(user, room_id, message_id):
    if not is_member(room_id, user):
        raise ChatActionError('forbidden', 'You are not a member of this room.')
    msg = message_queryset().filter(id=message_id, room_id=room_id, is_deleted=False).first()
    if msg is None:
        raise ChatActionError('not_found', 'Message not found.', status=404)
    if msg.sender_id != user.id:
        raise ChatActionError('forbidden', 'You can only change your own messages.')
    return msg


def edit_message(user, room_id, message_id, content):
    content = str(content or '').strip()
    if len(content) > MAX_CONTENT_CHARS:
        raise ChatActionError('too_long', f'Messages are limited to {MAX_CONTENT_CHARS} characters.', status=400)
    msg = _own_message(user, room_id, message_id)
    if msg.message_type == Message.TYPE_TEXT and not content:
        raise ChatActionError('bad_request', 'A message needs some text. Delete it instead.', status=400)
    if not can_send(msg.room, user):
        raise ChatActionError('forbidden', 'You can no longer message this person.')
    msg.content = content
    msg.is_edited = True
    msg.edited_at = timezone.now()
    msg.save(update_fields=['content', 'is_edited', 'edited_at', 'updated_at'])
    return msg


def delete_message(user, room_id, message_id):
    """Authors can always delete; the row stays as a tombstone with no content, file or transcript."""
    msg = _own_message(user, room_id, message_id)
    if msg.file:
        msg.file.delete(save=False)
    msg.is_deleted = True
    msg.content = ''
    msg.transcript = ''
    msg.file = None
    msg.save(update_fields=['is_deleted', 'content', 'transcript', 'file', 'updated_at'])
    MessageReaction.objects.filter(message=msg).delete()
    return msg


def set_reaction(user, room_id, message_id, reaction):
    """Set, change or (with ``None``) clear the user's single reaction on a message."""
    if reaction is not None and reaction not in MessageReaction.REACTIONS:
        raise ChatActionError('bad_request', 'Unknown reaction.', status=400)
    if not is_member(room_id, user):
        raise ChatActionError('forbidden', 'You are not a member of this room.')
    msg = Message.objects.select_related('room').filter(id=message_id, room_id=room_id, is_deleted=False).first()
    if msg is None:
        raise ChatActionError('not_found', 'Message not found.', status=404)
    if not can_send(msg.room, user):
        raise ChatActionError('forbidden', 'You can no longer message this person.')
    if reaction is None:
        MessageReaction.objects.filter(message=msg, user=user).delete()
    else:
        MessageReaction.objects.update_or_create(message=msg, user=user, defaults={'reaction': reaction})
    return {
        'type': 'message_reaction',
        'message_id': msg.id,
        'user_id': user.id,
        'reaction': reaction,
        'reactions': reaction_summary(MessageReaction.objects.filter(message=msg)),
    }


def mark_read(user, room_id, message_id):
    """Record a read receipt and move the member's read marker forward (never back)."""
    msg = Message.objects.filter(id=message_id, room_id=room_id).only('id', 'created_at').first()
    if msg is None:
        return False
    MessageRead.objects.get_or_create(message=msg, user=user)
    member = ChatMember.objects.filter(room_id=room_id, user=user)
    member.filter(last_read_at__isnull=True).update(last_read_at=msg.created_at)
    member.filter(last_read_at__lt=msg.created_at).update(last_read_at=msg.created_at)
    return True


def kick(room_id, user_id):
    """Tell the room a member is gone; their open socket closes itself."""
    broadcast(room_id, {'type': 'member_removed', 'user_id': user_id})


# ── Presence ──────────────────────────────────────────────────────────────────
# A user is online while they have at least one chat socket open. Counts live
# in the shared cache with a TTL, so a crashed worker can't pin someone online
# forever.

def _presence_key(user_id):
    return f'chat-online:{user_id}'


def mark_online(user_id):
    key = _presence_key(user_id)
    cache.add(key, 0, PRESENCE_TTL_SECONDS)
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, PRESENCE_TTL_SECONDS)
        return 1


def mark_offline(user_id):
    key = _presence_key(user_id)
    try:
        remaining = cache.decr(key)
    except ValueError:
        return 0
    if remaining <= 0:
        cache.delete(key)
    return max(remaining, 0)


def visible_online_ids(viewer, room_id):
    """Members of the room the viewer may see as online: opted in and not blocked either way."""
    blocked = visibility.blocked_ids(viewer)
    candidates = list(
        ChatMember.objects.filter(room_id=room_id, user__show_online_status=True)
        .exclude(user_id=viewer.id).exclude(user_id__in=blocked).values_list('user_id', flat=True)
    )
    if not candidates:
        return []
    counts = cache.get_many([_presence_key(uid) for uid in candidates])
    return [uid for uid in candidates if (counts.get(_presence_key(uid)) or 0) > 0]
