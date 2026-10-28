from django.conf import settings
from django.db import models


class FeedImpression(models.Model):
    """
    One post shown to one viewer in one feed page: the ranker's training signal.

    This is personal data (what someone looked at and for how long). It is
    never exposed to other members, only to the viewer's own debug view and as
    aggregates to staff, it cascades away with the viewer or the post, and a
    beat task deletes rows after ``RANKING_IMPRESSION_RETENTION_DAYS``.

    ``features`` is the feature vector computed when the page was served (in
    ``ranking.features.FEATURES`` order), so training sees exactly what
    serving saw, with no train/serve skew and no peeking at later data.
    """

    RANKER_V1 = 'v1'
    RANKER_V2 = 'v2'
    RANKER_LATEST = 'latest'

    viewer = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='feed_impressions', on_delete=models.CASCADE)
    post = models.ForeignKey('posts.Post', related_name='impressions', on_delete=models.CASCADE)
    position = models.PositiveIntegerField()
    # The experiment arm the viewer is assigned to ('' outside the experiment,
    # e.g. the chronological feed) and the ranker that actually ordered the
    # page (differs from the arm when v2 fell back to v1).
    variant = models.CharField(max_length=10, blank=True, default='')
    ranker = models.CharField(max_length=10)
    model_version = models.CharField(max_length=40, blank=True, default='')
    served_at = models.DateTimeField(db_index=True)
    engaged = models.BooleanField(default=False)
    engaged_at = models.DateTimeField(null=True, blank=True)
    dwell_ms = models.PositiveIntegerField(null=True, blank=True)
    features = models.JSONField(null=True, blank=True)
    # Written by ``simulate_feed_engagement`` for seed accounts only; training
    # and reports keep synthetic and real rows apart.
    synthetic = models.BooleanField(default=False)

    class Meta:
        db_table = 'feed_impressions'
        indexes = [
            models.Index(fields=['viewer', 'post', '-served_at'], name='impression_viewer_post'),
            models.Index(fields=['variant', 'served_at'], name='impression_variant_time'),
        ]

    def __str__(self):
        return f'Impression {self.viewer_id}→{self.post_id} @ {self.served_at:%Y-%m-%d %H:%M}'
