"""
WebSocket consumer for real-time chat.
URL: ws://host/ws/chat/<room_id>/?ticket=<one-time ticket>
"""
import logging
import json
import time

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_FRAME_BYTES = 16 * 1024
MAX_CONTENT_CHARS = 5000
# Token bucket: sustained 2 events/s, bursts of 10.
RATE_PER_SECOND = 2.0
BURST = 10


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'chat_{self.room_id}'
        self.user = user
        self._tokens = float(BURST)
        self._last = time.monotonic()

        if not await self.check_membership(user, self.room_id):
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        await self.broadcast_status('online')

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name') and hasattr(self, 'user'):
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

    async def send_error(self, code, detail):
        await self.send(text_data=json.dumps({'type': 'error', 'code': code, 'detail': detail}))

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
            await self.close(code=4003)
            return

        msg_type = data.get('type', 'message')
        if msg_type == 'message':
            await self.handle_message(data)
        elif msg_type == 'typing':
            await self.handle_typing(data)
        elif msg_type == 'read':
            await self.handle_read(data)

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

        reply_to_id = data.get('reply_to')
        reply_to_id = int(reply_to_id) if str(reply_to_id).isdigit() else None
        message = await self.save_message(content, reply_to_id)

        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'chat_message',
            'message_id': message.id,
            'content': message.content,
            'message_type': message.message_type,
            'sender_id': self.user.id,
            'sender_username': self.user.username,
            'sender_avatar': self.user.avatar.url if self.user.avatar else None,
            'reply_to': message.reply_to_id,
            'created_at': message.created_at.isoformat(),
        })
        await self.send_push_notifications(message)

    async def handle_typing(self, data):
        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'typing_indicator',
            'user_id': self.user.id,
            'username': self.user.username,
            'is_typing': bool(data.get('is_typing', False)),
        })

    async def handle_read(self, data):
        message_id = data.get('message_id')
        if str(message_id).isdigit() and await self.mark_message_read(int(message_id)):
            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'message_read',
                'message_id': int(message_id),
                'user_id': self.user.id,
            })

    # ── Channel layer event handlers ──────────────────────────

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({**event, 'type': 'message'}))

    async def typing_indicator(self, event):
        if event['user_id'] != self.user.id:
            await self.send(text_data=json.dumps({**event, 'type': 'typing'}))

    async def message_read(self, event):
        await self.send(text_data=json.dumps({**event, 'type': 'read'}))

    async def user_status(self, event):
        if event['user_id'] != self.user.id:
            await self.send(text_data=json.dumps({**event, 'type': 'status'}))

    # ── DB helpers ────────────────────────────────────────────

    @database_sync_to_async
    def check_membership(self, user, room_id):
        from .models import ChatMember
        return ChatMember.objects.filter(room_id=room_id, user=user).exists()

    @database_sync_to_async
    def can_send(self):
        from core import visibility
        from .models import ChatRoom
        room = ChatRoom.objects.get(id=self.room_id)
        if room.room_type != ChatRoom.TYPE_DIRECT:
            return True
        other = room.members.exclude(id=self.user.id).first()
        return other is None or visibility.can_message(self.user, other)

    @database_sync_to_async
    def save_message(self, content, reply_to_id):
        from .models import ChatRoom, Message
        if reply_to_id and not Message.objects.filter(id=reply_to_id, room_id=self.room_id).exists():
            reply_to_id = None
        msg = Message.objects.create(
            room_id=self.room_id,
            sender=self.user,
            content=content,
            message_type=Message.TYPE_TEXT,
            reply_to_id=reply_to_id,
        )
        ChatRoom.objects.filter(pk=self.room_id).update(updated_at=timezone.now())
        return msg

    @database_sync_to_async
    def mark_message_read(self, message_id):
        from .models import Message, MessageRead
        if not Message.objects.filter(id=message_id, room_id=self.room_id).exists():
            return False
        MessageRead.objects.get_or_create(message_id=message_id, user=self.user)
        return True

    @database_sync_to_async
    def send_push_notifications(self, message):
        try:
            from chats.tasks import notify_offline_members
            notify_offline_members.apply_async(
                args=[message.id, self.room_id, self.user.id],
                queue='messages',
            )
        except Exception:
            logger.warning('Background dispatch failed', exc_info=True)
