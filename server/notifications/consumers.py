"""
WebSocket consumer for real-time notifications.
URL: ws://host/ws/notifications/?token=<JWT>
"""
import json
from channels.generic.websocket import AsyncWebsocketConsumer


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        self.user = user
        self.group_name = f'notifications_{user.id}'

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data.get('type') == 'mark_read':
            await self.mark_notification_read(data.get('notification_id'))

    async def send_notification(self, event):
        """Called by channel layer when a notification is pushed."""
        await self.send(text_data=json.dumps({k: v for k, v in event.items() if k != 'type'}))

    async def mark_notification_read(self, notification_id):
        from channels.db import database_sync_to_async

        @database_sync_to_async
        def _mark():
            from notifications.models import Notification
            Notification.objects.filter(id=notification_id, recipient=self.user).update(is_read=True)

        await _mark()
