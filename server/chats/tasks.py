"""
Celery tasks for chat – processed via the 'messages' RabbitMQ queue.
"""
from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task(name='chats.tasks.notify_offline_members', queue='messages')
def notify_offline_members(message_id, room_id, sender_id):
    """
    Send push/email notifications to room members who are offline.
    Called after every new chat message.
    """
    from chats.models import Message, ChatMember
    from notifications.models import Notification

    try:
        message = Message.objects.select_related('sender', 'room').get(id=message_id)
        members = ChatMember.objects.filter(room_id=room_id).exclude(user_id=sender_id)

        for member in members:
            # Create in-app notification
            Notification.objects.create(
                recipient=member.user,
                sender=message.sender,
                notification_type=Notification.TYPE_MESSAGE,
                title=f'New message from {message.sender.username}',
                body=message.content[:100],
                extra={'room_id': room_id, 'message_id': message_id},
            )
    except Exception as e:
        logger.error(f'notify_offline_members failed: {e}')


@shared_task(name='chats.tasks.cleanup_old_messages', queue='default')
def cleanup_old_messages():
    """Soft-delete messages older than 1 year (configurable)."""
    from django.utils import timezone
    from datetime import timedelta
    from chats.models import Message

    cutoff = timezone.now() - timedelta(days=365)
    count = Message.objects.filter(created_at__lt=cutoff, is_deleted=False).update(is_deleted=True)
    logger.info(f'Soft-deleted {count} old messages.')
    return count
