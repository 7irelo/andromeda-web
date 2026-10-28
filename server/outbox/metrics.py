"""
Outbox and graph-drift metrics, read from Postgres at scrape time.

Celery workers aren't scraped, and Django runs several worker processes, so
anything kept in process memory would be partial. Reading the tables on each
scrape gives every process the same answer. The queries hit the partial
pending index and a four-row table, so they stay cheap.
"""
import logging

from django.utils import timezone
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

logger = logging.getLogger(__name__)


def _families():
    return {
        'pending': GaugeMetricFamily('outbox_pending_events', 'Outbox events not yet applied'),
        'age': GaugeMetricFamily('outbox_oldest_pending_age_seconds', 'Age of the oldest unapplied outbox event'),
        'dead': GaugeMetricFamily('outbox_dead_letter_events', 'Outbox events that gave up retrying'),
        'drift': CounterMetricFamily('graph_drift', 'Drift found (and repaired) by graph reconciliation',
                                     labels=['kind']),
        'last': GaugeMetricFamily('graph_drift_last_run', 'Drift found by the latest reconciliation run',
                                  labels=['kind']),
        'checked': GaugeMetricFamily('graph_reconcile_last_run_timestamp_seconds',
                                     'When graph reconciliation last completed'),
    }


class OutboxCollector:
    def describe(self):
        # Names only, without touching the database (called at registration time).
        return list(_families().values())

    def collect(self):
        from .models import GraphDrift, OutboxEvent

        f = _families()
        try:
            pending = OutboxEvent.objects.pending()
            oldest = pending.order_by('id').values_list('created_at', flat=True).first()
            f['pending'].add_metric([], pending.count())
            f['age'].add_metric([], (timezone.now() - oldest).total_seconds() if oldest else 0)
            f['dead'].add_metric([], OutboxEvent.objects.dead().count())
            latest = None
            for row in GraphDrift.objects.all():
                f['drift'].add_metric([row.kind], row.total)
                f['last'].add_metric([row.kind], row.last_run)
                if row.checked_at and (latest is None or row.checked_at > latest):
                    latest = row.checked_at
            if latest:
                f['checked'].add_metric([], latest.timestamp())
        except Exception:
            logger.warning('Outbox metrics unavailable', exc_info=True)
            return
        yield from f.values()


_registered = False


def register():
    global _registered
    if _registered:
        return
    from prometheus_client import REGISTRY

    REGISTRY.register(OutboxCollector())
    _registered = True
