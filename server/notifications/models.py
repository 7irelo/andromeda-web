from django.conf import settings
from django.db import models


class Notification(models.Model):
    TYPE_LIKE = 'like'
    TYPE_COMMENT = 'comment'
    TYPE_FRIEND_REQUEST = 'friend_request'
    TYPE_FRIEND_ACCEPTED = 'friend_accepted'
    TYPE_FOLLOW = 'follow'
    TYPE_MESSAGE = 'message'
    TYPE_GROUP_INVITE = 'group_invite'
    TYPE_POST_SHARE = 'post_share'
    TYPE_MENTION = 'mention'
    TYPE_SYSTEM = 'system'

    TYPE_CHOICES = [
        (TYPE_LIKE, 'Like'),
        (TYPE_COMMENT, 'Comment'),
        (TYPE_FRIEND_REQUEST, 'Friend Request'),
        (TYPE_FRIEND_ACCEPTED, 'Friend Accepted'),
        (TYPE_FOLLOW, 'Follow'),
        (TYPE_MESSAGE, 'Message'),
        (TYPE_GROUP_INVITE, 'Group Invite'),
        (TYPE_POST_SHARE, 'Post Share'),
        (TYPE_MENTION, 'Mention'),
        (TYPE_SYSTEM, 'System'),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='notifications',
        on_delete=models.CASCADE
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='sent_notifications',
        on_delete=models.SET_NULL, null=True, blank=True
    )
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    is_read = models.BooleanField(default=False)
    extra = models.JSONField(default=dict, blank=True)
    # Repeats of the same event on the same thing fold into one notification.
    group_key = models.CharField(max_length=120, blank=True, db_index=True)
    # False when the recipient only wants this category by email or push.
    in_app = models.BooleanField(default=True)
    emailed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-updated_at']
        indexes = [models.Index(fields=['recipient', 'is_read', '-updated_at'])]

    def __str__(self):
        return f'{self.notification_type} → {self.recipient.username}'

    def mark_read(self):
        self.is_read = True
        self.save(update_fields=['is_read'])


class NotificationPreference(models.Model):
    """Per-category channel choices, e.g. {"likes": {"in_app": true, "push": false, "email": false}}."""

    DIGEST_OFF = 'off'
    DIGEST_DAILY = 'daily'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name='notification_preference',
                                on_delete=models.CASCADE)
    channels = models.JSONField(default=dict, blank=True)
    email_digest = models.CharField(max_length=10, default=DIGEST_DAILY,
                                    choices=[(DIGEST_OFF, 'Off'), (DIGEST_DAILY, 'Daily')])
    # Opt-in weekly email of new listings near the user (replaces the old hourly spotlight).
    listing_digest = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)


class PushSubscription(models.Model):
    """A browser's Web Push endpoint. Keys are the browser's public keys, not secrets of ours."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='push_subscriptions', on_delete=models.CASCADE)
    endpoint = models.URLField(max_length=1000, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    user_agent = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
