"""
Celery tasks for notifications.
All tasks run on the 'notifications' RabbitMQ queue.
"""
from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import logging

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()


def _push_to_websocket(user_id, payload):
    """Push a notification payload to a user's WS group."""
    try:
        async_to_sync(channel_layer.group_send)(
            f'notifications_{user_id}',
            {'type': 'send_notification', **payload},
        )
    except Exception as e:
        logger.warning(f'WS push failed for user {user_id}: {e}')


@shared_task(name='notifications.tasks.send_like_notification', queue='notifications')
def send_like_notification(liker_id, post_author_id, post_id):
    if liker_id == post_author_id:
        return
    try:
        from django.contrib.auth import get_user_model
        from notifications.models import Notification
        User = get_user_model()
        liker = User.objects.get(id=liker_id)
        author = User.objects.get(id=post_author_id)

        notif = Notification.objects.create(
            recipient=author,
            sender=liker,
            notification_type=Notification.TYPE_LIKE,
            title=f'{liker.username} liked your post',
            extra={'post_id': post_id},
        )
        _push_to_websocket(post_author_id, {
            'id': notif.id,
            'type': 'like',
            'title': notif.title,
            'sender': liker.username,
            'sender_avatar': liker.avatar_url,
            'post_id': post_id,
            'created_at': notif.created_at.isoformat(),
        })
    except Exception as e:
        logger.error(f'send_like_notification error: {e}')


@shared_task(name='notifications.tasks.send_comment_notification', queue='notifications')
def send_comment_notification(commenter_id, post_author_id, post_id, comment_id):
    if commenter_id == post_author_id:
        return
    try:
        from django.contrib.auth import get_user_model
        from notifications.models import Notification
        User = get_user_model()
        commenter = User.objects.get(id=commenter_id)
        author = User.objects.get(id=post_author_id)

        notif = Notification.objects.create(
            recipient=author,
            sender=commenter,
            notification_type=Notification.TYPE_COMMENT,
            title=f'{commenter.username} commented on your post',
            extra={'post_id': post_id, 'comment_id': comment_id},
        )
        _push_to_websocket(post_author_id, {
            'id': notif.id,
            'type': 'comment',
            'title': notif.title,
            'sender': commenter.username,
            'sender_avatar': commenter.avatar_url,
            'post_id': post_id,
        })
    except Exception as e:
        logger.error(f'send_comment_notification error: {e}')


@shared_task(name='notifications.tasks.send_friend_request_notification', queue='notifications')
def send_friend_request_notification(sender_id, receiver_id, request_id):
    try:
        from django.contrib.auth import get_user_model
        from notifications.models import Notification
        User = get_user_model()
        sender = User.objects.get(id=sender_id)
        receiver = User.objects.get(id=receiver_id)

        notif = Notification.objects.create(
            recipient=receiver,
            sender=sender,
            notification_type=Notification.TYPE_FRIEND_REQUEST,
            title=f'{sender.username} sent you a friend request',
            extra={'request_id': request_id},
        )
        _push_to_websocket(receiver_id, {
            'id': notif.id,
            'type': 'friend_request',
            'title': notif.title,
            'sender': sender.username,
            'sender_avatar': sender.avatar_url,
            'request_id': request_id,
        })
    except Exception as e:
        logger.error(f'send_friend_request_notification error: {e}')


@shared_task(name='notifications.tasks.send_follow_notification', queue='notifications')
def send_follow_notification(follower_id, following_id):
    try:
        from django.contrib.auth import get_user_model
        from notifications.models import Notification
        User = get_user_model()
        follower = User.objects.get(id=follower_id)
        following = User.objects.get(id=following_id)

        notif = Notification.objects.create(
            recipient=following,
            sender=follower,
            notification_type=Notification.TYPE_FOLLOW,
            title=f'{follower.username} started following you',
        )
        _push_to_websocket(following_id, {
            'id': notif.id,
            'type': 'follow',
            'title': notif.title,
            'sender': follower.username,
            'sender_avatar': follower.avatar_url,
        })
    except Exception as e:
        logger.error(f'send_follow_notification error: {e}')


@shared_task(name='notifications.tasks.cleanup_old_notifications', queue='default')
def cleanup_old_notifications():
    """Delete read notifications older than 30 days."""
    from django.utils import timezone
    from datetime import timedelta
    from notifications.models import Notification

    cutoff = timezone.now() - timedelta(days=30)
    count, _ = Notification.objects.filter(is_read=True, created_at__lt=cutoff).delete()
    logger.info(f'Deleted {count} old notifications.')
    return count
