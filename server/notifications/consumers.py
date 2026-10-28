"""
WebSocket consumer for real-time notifications.
URL: ws://host/ws/notifications/?ticket=<one-time ticket>
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

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data or len(text_data) > 4096:
            return
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return
        if isinstance(data, dict) and data.get('type') == 'mark_read' and str(data.get('notification_id')).isdigit():
            await self.mark_notification_read(int(data['notification_id']))

    async def send_notification(self, event):
        """Called by channel layer when a notification is pushed."""
        await self.send(text_data=json.dumps({k: v for k, v in event.items() if k != 'type'}))

    async def feed_new_post(self, event):
        """A friend posted. Only the id is sent; the client fetches it through the visibility-checked API."""
        if isinstance(event.get('post_id'), int):
            await self.send(text_data=json.dumps({'type': 'feed.new_post', 'post_id': event['post_id']}))

    async def mark_notification_read(self, notification_id):
        from channels.db import database_sync_to_async

        @database_sync_to_async
        def _mark():
            from notifications.models import Notification
            Notification.objects.filter(id=notification_id, recipient=self.user).update(is_read=True)

        await _mark()
