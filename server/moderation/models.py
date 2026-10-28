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
    TYPE_MESSAGE = 'message'
    TYPE_USER = 'user'
    TYPE_VIDEO = 'video'
    TYPE_CHOICES = [(TYPE_POST, 'Post'), (TYPE_COMMENT, 'Comment'), (TYPE_LISTING, 'Listing'),
                    (TYPE_MESSAGE, 'Message'), (TYPE_USER, 'Profile'), (TYPE_VIDEO, 'Video')]

    SOURCE_AUTO = 'auto'
    SOURCE_REPORT = 'report'

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
    source = models.CharField(max_length=10, default=SOURCE_AUTO)
    # The text as it was when the case opened, kept as evidence if the author edits or deletes it.
    snapshot = models.TextField(blank=True)
    report_count = models.PositiveIntegerField(default=0)
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

    ACTION_CHOICES = [('approve', 'Approve'), ('remove', 'Remove'), ('restore', 'Restore'), ('warn', 'Warn'),
                      ('suspend', 'Suspend'), ('ban', 'Ban'), ('dismiss', 'Dismiss reports'),
                      ('uphold', 'Uphold on appeal')]

    case = models.ForeignKey(ModerationCase, on_delete=models.PROTECT, related_name='actions')
    moderator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    # For actions taken by an automated system rather than a person.
    automated_by = models.CharField(max_length=60, blank=True)
    note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'moderation_actions'
        ordering = ['-created_at']


class Report(models.Model):
    """A member's report about something they can see."""

    REASON_CHOICES = [
        ('spam', 'Spam'), ('harassment', 'Harassment or bullying'), ('hate', 'Hate speech'),
        ('violence', 'Violence or threats'), ('sexual', 'Sexual content'), ('scam', 'Scam or fraud'),
        ('illegal', 'Illegal goods or services'), ('self_harm', 'Self-harm'), ('privacy', 'Shares private information'),
        ('impersonation', 'Impersonation'), ('misinformation', 'False information'), ('other', 'Something else'),
    ]
    STATUS_OPEN = 'open'
    STATUS_ACTIONED = 'actioned'
    STATUS_DISMISSED = 'dismissed'

    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='reports_made', on_delete=models.CASCADE)
    content_type = models.CharField(max_length=10, choices=ModerationCase.TYPE_CHOICES)
    object_id = models.PositiveBigIntegerField()
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    details = models.CharField(max_length=1000, blank=True)
    case = models.ForeignKey(ModerationCase, related_name='reports', on_delete=models.CASCADE)
    status = models.CharField(max_length=10, default=STATUS_OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'moderation_reports'
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['reporter', 'content_type', 'object_id'],
                                               name='one_report_per_item')]


class Appeal(models.Model):
    """The author's request to have a removal looked at again by a person."""

    STATUS_OPEN = 'open'
    STATUS_UPHELD = 'upheld'
    STATUS_RESTORED = 'restored'

    case = models.OneToOneField(ModerationCase, related_name='appeal', on_delete=models.CASCADE)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='appeals', on_delete=models.CASCADE)
    message = models.CharField(max_length=1000, blank=True)
    status = models.CharField(max_length=10, default=STATUS_OPEN)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='appeals_decided')
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'moderation_appeals'
        ordering = ['-created_at']
