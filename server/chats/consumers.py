"""
WebSocket consumer for real-time chat.
URL: ws://host/ws/chat/<room_id>/?token=<JWT>
"""
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'chat_{self.room_id}'
        self.user = user

        # Verify the user is a member of the room
        is_member = await self.check_membership(user, self.room_id)
        if not is_member:
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # Notify others user is online
        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'user_status',
            'user_id': user.id,
            'username': user.username,
            'status': 'online',
        })

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'user_status',
                'user_id': self.user.id,
                'username': self.user.username,
                'status': 'offline',
            })
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        msg_type = data.get('type', 'message')

        if msg_type == 'message':
            await self.handle_message(data)
        elif msg_type == 'typing':
            await self.handle_typing(data)
        elif msg_type == 'read':
            await self.handle_read(data)

    async def handle_message(self, data):
        content = data.get('content', '').strip()
        message_type = data.get('message_type', 'text')
        reply_to_id = data.get('reply_to')

        if not content and message_type == 'text':
            return

        # Persist to DB
        message = await self.save_message(content, message_type, reply_to_id)

        # Broadcast to room
        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'chat_message',
            'message_id': message.id,
            'content': message.content,
            'message_type': message.message_type,
            'sender_id': self.user.id,
            'sender_username': self.user.username,
            'sender_avatar': self.user.avatar_url,
            'reply_to': reply_to_id,
            'created_at': message.created_at.isoformat(),
        })

        # Queue push notification via RabbitMQ/Celery for offline members
        await self.send_push_notifications(message)

    async def handle_typing(self, data):
        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'typing_indicator',
            'user_id': self.user.id,
            'username': self.user.username,
            'is_typing': data.get('is_typing', False),
        })

    async def handle_read(self, data):
        message_id = data.get('message_id')
        if message_id:
            await self.mark_message_read(message_id)
            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'message_read',
                'message_id': message_id,
                'user_id': self.user.id,
            })

    # ── Channel layer event handlers ──────────────────────────

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({'type': 'message', **event}))

    async def typing_indicator(self, event):
        if event['user_id'] != self.user.id:
            await self.send(text_data=json.dumps({'type': 'typing', **event}))

    async def message_read(self, event):
        await self.send(text_data=json.dumps({'type': 'read', **event}))

    async def user_status(self, event):
        if event['user_id'] != self.user.id:
            await self.send(text_data=json.dumps({'type': 'status', **event}))

    async def notification(self, event):
        await self.send(text_data=json.dumps({'type': 'notification', **event}))

    # ── DB helpers ────────────────────────────────────────────

    @database_sync_to_async
    def check_membership(self, user, room_id):
        from .models import ChatMember
        return ChatMember.objects.filter(room_id=room_id, user=user).exists()

    @database_sync_to_async
    def save_message(self, content, message_type, reply_to_id):
        from .models import Message, ChatRoom
        room = ChatRoom.objects.get(id=self.room_id)
        msg = Message.objects.create(
            room=room,
            sender=self.user,
            content=content,
            message_type=message_type,
            reply_to_id=reply_to_id,
        )
        # Update room's updated_at
        ChatRoom.objects.filter(pk=self.room_id).update(updated_at=timezone.now())
        return msg

    @database_sync_to_async
    def mark_message_read(self, message_id):
        from .models import MessageRead
        MessageRead.objects.get_or_create(message_id=message_id, user=self.user)

    @database_sync_to_async
    def send_push_notifications(self, message):
        try:
            from chats.tasks import notify_offline_members
            notify_offline_members.apply_async(
                args=[message.id, self.room_id, self.user.id],
                queue='messages',
            )
        except Exception:
            pass
