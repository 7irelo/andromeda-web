from django.conf import settings
from django.db import models

from core.validators import RandomFilename


class Video(models.Model):
    STATUS_PROCESSING = 'processing'
    STATUS_READY = 'ready'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_READY, 'Ready'),
        (STATUS_FAILED, 'Failed'),
    ]

    CAPTIONS_NONE = 'none'
    CAPTIONS_PENDING = 'pending'
    CAPTIONS_READY = 'ready'
    CAPTIONS_UNAVAILABLE = 'unavailable'
    CAPTIONS_CHOICES = [
        (CAPTIONS_NONE, 'None'),
        (CAPTIONS_PENDING, 'Pending'),
        (CAPTIONS_READY, 'Ready'),
        (CAPTIONS_UNAVAILABLE, 'Unavailable'),
    ]

    uploader = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='videos', on_delete=models.CASCADE
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    # The original upload is never served: viewers get the HLS renditions.
    video_file = models.FileField(upload_to=RandomFilename('private/watch/originals'))
    # Optional custom thumbnail; processing copies it into the asset folder.
    thumbnail = models.ImageField(upload_to=RandomFilename('private/watch/uploads'), null=True, blank=True)
    duration = models.PositiveIntegerField(default=0, help_text='Seconds')
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_PROCESSING)
    failure_reason = models.CharField(max_length=255, blank=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    # Processed assets live at ``<asset_root>/watch/hls/<asset_id>/``. The root
    # is ``public`` (served by nginx) only while the video is public.
    asset_root = models.CharField(max_length=10, blank=True)
    asset_id = models.CharField(max_length=32, blank=True)
    asset_files = models.JSONField(default=list, blank=True)
    renditions = models.JSONField(default=list, blank=True)
    views_count = models.PositiveIntegerField(default=0)
    likes_count = models.PositiveIntegerField(default=0)
    comments_count = models.PositiveIntegerField(default=0)
    is_public = models.BooleanField(default=True)
    moderation_status = models.CharField(max_length=10, default='ok', db_index=True,
                                         choices=[('ok', 'OK'), ('review', 'In review'), ('removed', 'Removed')])
    tags = models.JSONField(default=list, blank=True)
    captions_status = models.CharField(max_length=15, choices=CAPTIONS_CHOICES, default=CAPTIONS_NONE)
    transcript = models.TextField(blank=True)
    transcript_language = models.CharField(max_length=16, blank=True)
    captions_vtt = models.TextField(blank=True)
    chapters = models.JSONField(default=list, blank=True)
    subscribers_notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'videos'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class VideoView(models.Model):
    video = models.ForeignKey(Video, related_name='views', on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    watch_time = models.PositiveIntegerField(default=0, help_text='Seconds watched')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'video_views'
        constraints = [
            # One counted view per signed-in viewer.
            models.UniqueConstraint(fields=['video', 'user'], condition=models.Q(user__isnull=False),
                                    name='video_view_once_per_user'),
        ]


class VideoLike(models.Model):
    video = models.ForeignKey(Video, related_name='likes', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'video_likes'
        unique_together = ('video', 'user')


class VideoComment(models.Model):
    video = models.ForeignKey(Video, related_name='comments', on_delete=models.CASCADE)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField()
    parent = models.ForeignKey('self', null=True, blank=True, related_name='replies', on_delete=models.CASCADE)
    likes_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'video_comments'
        ordering = ['created_at']


class WatchProgress(models.Model):
    """Where a viewer left off. One row per (user, video); doubles as watch history."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='watch_progress', on_delete=models.CASCADE)
    video = models.ForeignKey(Video, related_name='progress', on_delete=models.CASCADE)
    position_s = models.FloatField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'video_watch_progress'
        constraints = [models.UniqueConstraint(fields=['user', 'video'], name='watch_progress_once')]
        indexes = [models.Index(fields=['user', '-updated_at'])]


class ChannelSubscription(models.Model):
    subscriber = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='channel_subscriptions',
                                   on_delete=models.CASCADE)
    channel = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='channel_subscribers',
                                on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'video_channel_subscriptions'
        constraints = [
            models.UniqueConstraint(fields=['subscriber', 'channel'], name='channel_subscription_once'),
            models.CheckConstraint(condition=~models.Q(subscriber=models.F('channel')), name='no_self_subscription'),
        ]
