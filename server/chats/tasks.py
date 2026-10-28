"""
Celery tasks for chat – processed via the 'messages' RabbitMQ queue.
"""
from celery import shared_task
import logging
import os

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
                body=message.content[:100] or ('Sent a voice message' if message.message_type == 'voice' else ''),
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


TRANSCRIBE_MAX_RETRIES = 3
MAX_TRANSCRIPT_CHARS = 20_000


@shared_task(bind=True, name='chats.tasks.transcribe_voice_note', queue='messages',
             max_retries=TRANSCRIBE_MAX_RETRIES)
def transcribe_voice_note(self, message_id):
    """
    Transcribe a voice note through the AI service and push the result to the room.

    Idempotent: a message that is gone, deleted, not a voice note or already
    transcribed is left alone. Outages are retried a few times with backoff;
    after that, or if the AI service refuses the audio, the voice note simply
    stays without a transcript.
    """
    import base64

    from core import ai_client
    from chats import services
    from chats.audio import MIMETYPE_BY_EXT
    from chats.models import Message

    msg = Message.objects.select_related('sender').filter(id=message_id).first()
    if (msg is None or msg.is_deleted or msg.message_type != Message.TYPE_VOICE or not msg.file
            or msg.transcript_status == Message.TRANSCRIPT_DONE):
        return None

    def finish(status, transcript=''):
        Message.objects.filter(id=message_id, is_deleted=False).update(
            transcript_status=status, transcript=transcript[:MAX_TRANSCRIPT_CHARS])
        fresh = services.message_queryset().filter(id=message_id).first()
        if fresh is not None:
            services.broadcast(fresh.room_id, {'type': 'message_updated', 'message': services.payload(fresh)})
        return status

    if not ai_client.enabled() or (msg.sender and msg.sender.ai_opt_out):
        return finish(Message.TRANSCRIPT_FAILED)

    mimetype = MIMETYPE_BY_EXT.get(os.path.splitext(msg.file.name)[1].lower())
    if mimetype is None:
        return finish(Message.TRANSCRIPT_FAILED)
    with msg.file.open('rb') as fh:
        audio_b64 = base64.b64encode(fh.read()).decode('ascii')

    try:
        result = ai_client.call('/v1/transcribe', {
            'audio_b64': audio_b64, 'mimetype': mimetype, 'purpose': 'voice_note',
        }, user_id=msg.sender_id)
    except ai_client.AIRejected as exc:
        logger.info('Voice note %s not transcribed: %s', message_id, exc.detail)
        return finish(Message.TRANSCRIPT_FAILED)
    except ai_client.AIUnavailable as exc:
        if self.request.retries >= TRANSCRIBE_MAX_RETRIES:
            logger.warning('Voice note %s not transcribed: AI service unavailable', message_id)
            return finish(Message.TRANSCRIPT_FAILED)
        raise self.retry(exc=exc, countdown=30 * 2 ** self.request.retries)

    return finish(Message.TRANSCRIPT_DONE, str(result.get('transcript') or '').strip())
