from django.conf import settings
from django.db import models

STATUS_OK = 'ok'
STATUS_REVIEW = 'review'
STATUS_REMOVED = 'removed'
STATUS_CHOICES = [(STATUS_OK, 'OK'), (STATUS_REVIEW, 'In review'), (STATUS_REMOVED, 'Removed')]


class ModerationCase(models.Model):
    """One automated (or human) decision about one piece of content."""

    TYPE_POST = 'post'
    TYPE_COMMENT = 'comment'
    TYPE_LISTING = 'listing'
    TYPE_CHOICES = [(TYPE_POST, 'Post'), (TYPE_COMMENT, 'Comment'), (TYPE_LISTING, 'Listing')]

    DECISION_CHOICES = [('allow', 'Allow'), ('review', 'Review'), ('remove', 'Remove')]

    content_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    object_id = models.PositiveBigIntegerField()
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                               related_name='moderation_cases')
    decision = models.CharField(max_length=10, choices=DECISION_CHOICES)
    categories = models.JSONField(default=list)
    confidence = models.FloatField(default=0)
    reason = models.CharField(max_length=300, blank=True)
    model = models.CharField(max_length=60, blank=True)
    stages = models.JSONField(default=list)
    degraded = models.BooleanField(default=False)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    # Human resolution (append-only audit lives in ModerationAction).
    resolved = models.BooleanField(default=False)

    class Meta:
        db_table = 'moderation_cases'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['content_type', 'object_id']),
                   models.Index(fields=['resolved', 'decision'])]


class ModerationAction(models.Model):
    """Append-only audit log of every human moderation action."""

    ACTION_CHOICES = [('approve', 'Approve'), ('remove', 'Remove'), ('restore', 'Restore')]

    case = models.ForeignKey(ModerationCase, on_delete=models.PROTECT, related_name='actions')
    moderator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'moderation_actions'
        ordering = ['-created_at']
