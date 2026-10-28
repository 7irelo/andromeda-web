from django.db import models
from django.db.models import Q
from django.utils import timezone


class OutboxEventQuerySet(models.QuerySet):
    def pending(self):
        return self.filter(processed_at__isnull=True, dead_at__isnull=True)

    def dead(self):
        return self.filter(dead_at__isnull=False)


class OutboxEvent(models.Model):
    """One side effect to apply after the change that produced it has committed."""

    id = models.BigAutoField(primary_key=True)
    kind = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    processed_at = models.DateTimeField(null=True, blank=True)
    # Set when the event gave up after OUTBOX_MAX_ATTEMPTS (or can never succeed).
    dead_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    objects = OutboxEventQuerySet.as_manager()

    class Meta:
        db_table = 'outbox_events'
        ordering = ['id']
        indexes = [
            # The drain's only query: due, unprocessed, live events in id order.
            models.Index(fields=['next_attempt_at', 'id'], name='outbox_pending_idx',
                         condition=Q(processed_at__isnull=True, dead_at__isnull=True)),
            models.Index(fields=['processed_at'], name='outbox_processed_idx'),
        ]

    def __str__(self):
        return f'{self.kind} #{self.id}'


class GraphDrift(models.Model):
    """Running totals from the nightly graph reconciliation, exported as ``graph_drift_total{kind}``."""

    kind = models.CharField(max_length=32, primary_key=True)
    total = models.PositiveBigIntegerField(default=0)
    last_run = models.PositiveIntegerField(default=0)
    checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'outbox_graph_drift'

    def __str__(self):
        return f'{self.kind}: {self.last_run} (total {self.total})'
