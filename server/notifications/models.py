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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.notification_type} → {self.recipient.username}'

    def mark_read(self):
        self.is_read = True
        self.save(update_fields=['is_read'])
