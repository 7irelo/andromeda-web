from django.db.models.signals import post_save
from django.dispatch import receiver
from users.models import FriendRequest, Follow


@receiver(post_save, sender=FriendRequest)
def notify_on_friend_request(sender, instance, created, **kwargs):
    if created:
        try:
            from notifications.tasks import send_friend_request_notification
            send_friend_request_notification.apply_async(
                args=[instance.sender_id, instance.receiver_id, instance.id],
                queue='notifications',
            )
        except Exception:
            pass


@receiver(post_save, sender=Follow)
def notify_on_follow(sender, instance, created, **kwargs):
    if created:
        try:
            from notifications.tasks import send_follow_notification
            send_follow_notification.apply_async(
                args=[instance.follower_id, instance.following_id],
                queue='notifications',
            )
        except Exception:
            pass
