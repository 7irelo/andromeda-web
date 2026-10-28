"""
Celery tasks for notifications.
Delivery tasks run on the 'notifications' queue; emails on 'emails'.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)


def _push_to_websocket(user_id, payload):
    """Kept for callers that push non-notification events (e.g. feed updates)."""
    from .service import push_websocket
    push_websocket(user_id, payload)


@shared_task(name='notifications.tasks.send_like_notification', queue='notifications')
def send_like_notification(liker_id, post_author_id, post_id):
    from .models import Notification
    from .service import notify
    liker = get_user_model().objects.filter(id=liker_id).first()
    if liker is None:
        return
    notify(post_author_id, Notification.TYPE_LIKE, f'{liker.username} liked your post', sender=liker,
           extra={'post_id': post_id}, group_key=f'like:post:{post_id}', group_verb='liked your post',
           push_url=f'/posts/{post_id}')


@shared_task(name='notifications.tasks.send_comment_notification', queue='notifications')
def send_comment_notification(commenter_id, post_author_id, post_id, comment_id):
    from .models import Notification
    from .service import notify
    commenter = get_user_model().objects.filter(id=commenter_id).first()
    if commenter is None:
        return
    notify(post_author_id, Notification.TYPE_COMMENT, f'{commenter.username} commented on your post',
           sender=commenter, extra={'post_id': post_id, 'comment_id': comment_id},
           group_key=f'comment:post:{post_id}', group_verb='commented on your post', push_url=f'/posts/{post_id}')


@shared_task(name='notifications.tasks.send_friend_request_notification', queue='notifications')
def send_friend_request_notification(sender_id, receiver_id, request_id):
    from .models import Notification
    from .service import notify
    sender = get_user_model().objects.filter(id=sender_id).first()
    if sender is None:
        return
    notify(receiver_id, Notification.TYPE_FRIEND_REQUEST, f'{sender.username} sent you a friend request',
           sender=sender, extra={'request_id': request_id}, push_url='/friends')


@shared_task(name='notifications.tasks.send_follow_notification', queue='notifications')
def send_follow_notification(follower_id, following_id):
    from .models import Notification
    from .service import notify
    follower = get_user_model().objects.filter(id=follower_id).first()
    if follower is None:
        return
    notify(following_id, Notification.TYPE_FOLLOW, f'{follower.username} started following you', sender=follower,
           group_key=f'follow:{following_id}', group_verb='started following you')


@shared_task(name='notifications.tasks.deliver_web_push', queue='notifications')
def deliver_web_push(user_id, title, body, url=''):
    from pywebpush import WebPushException, webpush

    from .models import PushSubscription
    from .service import push_enabled, web_push_payload
    if not push_enabled():
        return 0
    sent = 0
    for sub in PushSubscription.objects.filter(user_id=user_id):
        try:
            webpush(
                subscription_info={'endpoint': sub.endpoint, 'keys': {'p256dh': sub.p256dh, 'auth': sub.auth}},
                data=web_push_payload(title, body, url),
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={'sub': settings.VAPID_SUBJECT},
                timeout=10,
            )
            sent += 1
        except WebPushException as exc:
            status = getattr(exc.response, 'status_code', None)
            if status in (404, 410):  # the browser dropped the subscription
                sub.delete()
            else:
                logger.warning('Web push failed (%s)', status)
    return sent


@shared_task(name='notifications.tasks.send_notification_email', queue='emails')
def send_notification_email(notification_id):
    from .models import Notification
    n = Notification.objects.select_related('recipient').filter(pk=notification_id, emailed_at__isnull=True).first()
    if n is None or not n.recipient.is_active:
        return
    send_mail(
        subject=n.title[:120], from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[n.recipient.email],
        message=f'{n.title}\n\n{n.body}\n\nOpen Andromeda: {settings.FRONTEND_URL}/notifications\n\n'
                f'Manage email notifications: {settings.FRONTEND_URL}/settings',
        fail_silently=True,
    )
    Notification.objects.filter(pk=n.pk).update(emailed_at=timezone.now())


@shared_task(name='notifications.tasks.send_daily_digests', queue='emails')
def send_daily_digests():
    """One email per opted-in user summarising unread notifications from the last day."""
    from .models import Notification, NotificationPreference
    since = timezone.now() - timedelta(days=1)
    opted_out = NotificationPreference.objects.filter(
        email_digest=NotificationPreference.DIGEST_OFF).values_list('user_id', flat=True)
    pending = (Notification.objects.filter(is_read=False, emailed_at__isnull=True, updated_at__gte=since,
                                           recipient__is_active=True)
               .exclude(recipient_id__in=opted_out).select_related('recipient').order_by('recipient_id', '-updated_at'))
    by_user = {}
    for n in pending[:20000]:
        by_user.setdefault(n.recipient, []).append(n)
    for user, items in by_user.items():
        lines = [f'- {n.title}' for n in items[:15]]
        more = len(items) - 15
        if more > 0:
            lines.append(f'...and {more} more')
        send_mail(
            subject=f'You have {len(items)} new notification{"s" if len(items) != 1 else ""} on Andromeda',
            message='\n'.join(lines) + f'\n\nOpen Andromeda: {settings.FRONTEND_URL}/notifications\n\n'
                    f'Turn off the daily email: {settings.FRONTEND_URL}/settings',
            from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[user.email], fail_silently=True,
        )
        Notification.objects.filter(pk__in=[n.pk for n in items]).update(emailed_at=timezone.now())
    return len(by_user)


@shared_task(name='notifications.tasks.send_listing_digests', queue='emails')
def send_listing_digests():
    """
    Opt-in weekly digest of new listings near the user (same city), as one
    bulk insert of in-app notifications plus one email each.
    """
    from core import visibility
    from marketplace.models import Listing

    from .models import Notification
    since = timezone.now() - timedelta(days=7)
    users = get_user_model().objects.filter(
        notification_preference__listing_digest=True, is_active=True).exclude(location='')
    rows = []
    for user in users.iterator():
        city = user.location.split(',')[0].strip()
        listings = list(Listing.objects.filter(status=Listing.STATUS_ACTIVE, created_at__gte=since,
                                               location__icontains=city)
                        .exclude(moderation_status='removed').exclude(seller=user)
                        .exclude(seller_id__in=visibility.blocked_ids(user)).order_by('-created_at')[:5])
        if not listings:
            continue
        title = f'{len(listings)} new listing{"s" if len(listings) != 1 else ""} near {city} this week'
        rows.append(Notification(recipient=user, notification_type=Notification.TYPE_SYSTEM, title=title,
                                 extra={'kind': 'listing_digest', 'listing_ids': [x.id for x in listings]}))
        send_mail(subject=title, from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[user.email],
                  message='\n'.join(f'- {x.title}: {x.currency} {x.price}' for x in listings)
                  + f'\n\n{settings.FRONTEND_URL}/marketplace\n\nStop these emails: {settings.FRONTEND_URL}/settings',
                  fail_silently=True)
    Notification.objects.bulk_create(rows, batch_size=500)
    return len(rows)


@shared_task(name='notifications.tasks.cleanup_old_notifications', queue='default')
def cleanup_old_notifications():
    """Delete read notifications older than 30 days."""
    from .models import Notification

    cutoff = timezone.now() - timedelta(days=30)
    count, _ = Notification.objects.filter(is_read=True, updated_at__lt=cutoff).delete()
    logger.info('Deleted %s old notifications.', count)
    return count
