"""
WebSocket consumer for real-time chat.
URL: ws://host/ws/chat/<room_id>/?ticket=<one-time ticket>

Client frames: message, typing, read, edit, delete, react.
Server frames: message, message_updated, reaction, typing, read, status,
presence, room_updated, member_removed, error.
"""
import logging
import json
import time

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from . import services

logger = logging.getLogger(__name__)

MAX_FRAME_BYTES = 16 * 1024
MAX_CONTENT_CHARS = services.MAX_CONTENT_CHARS
# Token bucket: sustained 2 events/s, bursts of 10. Shared by every frame type.
RATE_PER_SECOND = 2.0
BURST = 10
# Outgoing events re-check membership and blocks at most this often; removals
# also push an explicit member_removed event that closes the socket at once.
RECHECK_SECONDS = 30


def _int(value):
    return int(value) if str(value).isdigit() else None


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        self.room_id = int(self.scope['url_route']['kwargs']['room_id'])
        self.user = user
        self._tokens = float(BURST)
        self._last = time.monotonic()

        if not await self.check_membership(user, self.room_id):
            await self.close(code=4003)
            return

        self.room_group_name = services.group_name(self.room_id)
        self._member = True
        self._blocked = await self.load_blocked()
        self._checked_at = time.monotonic()
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        await database_sync_to_async(services.mark_online)(self.user.id)
        await self.broadcast_status('online')
        await self.send_json({'type': 'presence', 'online': await self.visible_online()})

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name') and hasattr(self, 'user'):
            remaining = await database_sync_to_async(services.mark_offline)(self.user.id)
            if not remaining:
                await self.broadcast_status('offline')
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def broadcast_status(self, status):
        if not self.user.show_online_status:
            return
        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'user_status',
            'user_id': self.user.id,
            'username': self.user.username,
            'status': status,
        })

    def _allow(self):
        now = time.monotonic()
        self._tokens = min(BURST, self._tokens + (now - self._last) * RATE_PER_SECOND)
        self._last = now
        if self._tokens < 1:
            return False
        self._tokens -= 1
        return True

    async def send_json(self, data):
        await self.send(text_data=json.dumps(data))

    async def send_error(self, code, detail):
        await self.send_json({'type': 'error', 'code': code, 'detail': detail})

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data or len(text_data) > MAX_FRAME_BYTES:
            await self.close(code=4009)
            return
        if not self._allow():
            await self.send_error('rate_limited', 'Slow down.')
            return
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send_error('bad_request', 'Invalid JSON.')
            return
        if not isinstance(data, dict):
            return

        # Membership can be revoked while connected (removed, left, blocked).
        if not await self.check_membership(self.user, self.room_id):
            self._member = False
            await self.close(code=4003)
            return

        handler = {
            'message': self.handle_message,
            'typing': self.handle_typing,
            'read': self.handle_read,
            'edit': self.handle_edit,
            'delete': self.handle_delete,
            'react': self.handle_react,
        }.get(data.get('type', 'message'))
        if handler:
            await handler(data)

    async def handle_message(self, data):
        content = str(data.get('content', '')).strip()
        if not content:
            return
        if len(content) > MAX_CONTENT_CHARS:
            await self.send_error('too_long', f'Messages are limited to {MAX_CONTENT_CHARS} characters.')
            return
        if not await self.can_send():
            await self.send_error('forbidden', 'You can no longer message this person.')
            return

        message_id, message = await self.save_message(content, _int(data.get('reply_to')))
        await self.channel_layer.group_send(self.room_group_name, {'type': 'chat_message', 'message': message})
        await self.send_push_notifications(message_id)

    async def handle_typing(self, data):
        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'typing_indicator',
            'user_id': self.user.id,
            'username': self.user.username,
            'is_typing': bool(data.get('is_typing', False)),
        })

    async def handle_read(self, data):
        message_id = _int(data.get('message_id'))
        if message_id and await database_sync_to_async(services.mark_read)(self.user, self.room_id, message_id):
            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'message_read',
                'message_id': message_id,
                'user_id': self.user.id,
            })

    async def _run(self, action, *args):
        """Run a shared chat action; report refusals to this socket only."""
        try:
            return await database_sync_to_async(action)(self.user, self.room_id, *args)
        except services.ChatActionError as exc:
            await self.send_error(exc.code, exc.detail)
            return None

    async def handle_edit(self, data):
        message_id = _int(data.get('message_id'))
        if not message_id:
            return
        msg = await self._run(services.edit_message, message_id, data.get('content', ''))
        if msg is not None:
            await self.broadcast_update(msg)

    async def handle_delete(self, data):
        message_id = _int(data.get('message_id'))
        if not message_id:
            return
        msg = await self._run(services.delete_message, message_id)
        if msg is not None:
            await self.broadcast_update(msg)

    async def handle_react(self, data):
        message_id = _int(data.get('message_id'))
        reaction = data.get('reaction')
        if not message_id or not (reaction is None or isinstance(reaction, str)):
            return
        event = await self._run(services.set_reaction, message_id, reaction or None)
        if event is not None:
            await self.channel_layer.group_send(self.room_group_name, event)

    async def broadcast_update(self, msg):
        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'message_updated', 'message': await database_sync_to_async(services.payload)(msg),
        })

    # ── Channel layer event handlers ──────────────────────────

    async def _may_receive(self):
        """Cheap periodic re-check so a missed removal event can't leave a socket listening."""
        if not self._member:
            return False
        if time.monotonic() - self._checked_at > RECHECK_SECONDS:
            self._checked_at = time.monotonic()
            self._member = await self.check_membership(self.user, self.room_id)
            self._blocked = await self.load_blocked()
            if not self._member:
                await self.close(code=4003)
        return self._member

    async def chat_message(self, event):
        if await self._may_receive():
            await self.send_json({'type': 'message', 'message': event['message']})

    async def message_updated(self, event):
        if await self._may_receive():
            await self.send_json({'type': 'message_updated', 'message': event['message']})

    async def message_reaction(self, event):
        if await self._may_receive():
            await self.send_json({**event, 'type': 'reaction'})

    async def room_updated(self, event):
        if await self._may_receive():
            await self.send_json({'type': 'room_updated', 'room_id': self.room_id})

    async def member_removed(self, event):
        if event['user_id'] == self.user.id:
            self._member = False
            await self.send_json({'type': 'member_removed', 'user_id': self.user.id})
            await self.close(code=4003)
        elif await self._may_receive():
            await self.send_json({'type': 'member_removed', 'user_id': event['user_id']})

    async def typing_indicator(self, event):
        if event['user_id'] != self.user.id and event['user_id'] not in self._blocked and await self._may_receive():
            await self.send_json({**event, 'type': 'typing'})

    async def message_read(self, event):
        if event['user_id'] not in self._blocked and await self._may_receive():
            await self.send_json({**event, 'type': 'read'})

    async def user_status(self, event):
        if event['user_id'] != self.user.id and event['user_id'] not in self._blocked and await self._may_receive():
            await self.send_json({**event, 'type': 'status'})

    # ── DB helpers ────────────────────────────────────────────

    @database_sync_to_async
    def check_membership(self, user, room_id):
        return services.is_member(room_id, user)

    @database_sync_to_async
    def load_blocked(self):
        from core import visibility
        return visibility.blocked_ids(self.user)

    @database_sync_to_async
    def visible_online(self):
        return services.visible_online_ids(self.user, self.room_id)

    @database_sync_to_async
    def can_send(self):
        from .models import ChatRoom
        return services.can_send(ChatRoom.objects.get(id=self.room_id), self.user)

    @database_sync_to_async
    def save_message(self, content, reply_to_id):
        from django.utils import timezone
        from .models import ChatRoom, Message
        if reply_to_id and not Message.objects.filter(
                id=reply_to_id, room_id=self.room_id, is_deleted=False).exists():
            reply_to_id = None
        msg = Message.objects.create(
            room_id=self.room_id,
            sender=self.user,
            content=content,
            message_type=Message.TYPE_TEXT,
            reply_to_id=reply_to_id,
        )
        ChatRoom.objects.filter(pk=self.room_id).update(updated_at=timezone.now())
        return msg.id, services.payload(services.message_queryset().get(pk=msg.pk))

    @database_sync_to_async
    def send_push_notifications(self, message_id):
        try:
            from chats.tasks import notify_offline_members
            notify_offline_members.apply_async(
                args=[message_id, self.room_id, self.user.id],
                queue='messages',
            )
        except Exception:
            logger.warning('Background dispatch failed', exc_info=True)
