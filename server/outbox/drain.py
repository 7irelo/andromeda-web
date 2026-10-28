"""
Applying outbox events.

One batch at a time, in id order, inside a transaction that row-locks the
batch with ``SKIP LOCKED``: concurrent drains (several workers, an overlapping
beat tick) take disjoint batches and never apply the same event twice at once.
A failing event is rescheduled with exponential backoff and jitter and the
batch moves on; a connection failure stops the batch early so one outage
doesn't burn an attempt on every queued event.
"""
import logging
import random
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .handlers import HANDLERS
from .models import OutboxEvent

logger = logging.getLogger(__name__)

UPDATE_FIELDS = ['attempts', 'next_attempt_at', 'processed_at', 'dead_at', 'last_error']


def _setting(name, default):
    return getattr(settings, name, default)


def backoff_seconds(attempts):
    """Delay before attempt ``attempts + 1``: exponential, capped, with "equal jitter" (half fixed, half random)."""
    base = _setting('OUTBOX_BACKOFF_BASE_SECONDS', 5)
    cap = _setting('OUTBOX_BACKOFF_MAX_SECONDS', 3600)
    delay = min(cap, base * 2 ** max(0, attempts - 1))
    return delay / 2 + random.uniform(0, delay / 2)


def _is_connection_error(exc):
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    return type(exc).__module__.startswith('neo4j') and type(exc).__name__ in (
        'ServiceUnavailable', 'SessionExpired', 'AuthError')


def _describe(exc):
    # Exception text only: payloads stay out of logs and the error column.
    return f'{type(exc).__name__}: {exc}'[:1000]


def _fail(event, exc, now):
    event.attempts += 1
    event.last_error = _describe(exc)
    if event.attempts >= _setting('OUTBOX_MAX_ATTEMPTS', 12):
        event.dead_at = now
        logger.error('Outbox event %s (%s) dead-lettered after %s attempts: %s',
                     event.id, event.kind, event.attempts, event.last_error)
    else:
        event.next_attempt_at = now + timedelta(seconds=backoff_seconds(event.attempts))
        logger.warning('Outbox event %s (%s) failed, attempt %s: %s',
                       event.id, event.kind, event.attempts, event.last_error)


def drain(graph=None, batch_size=None, now=None):
    """Apply one batch of due events. Returns ``{'processed': n, 'failed': n, 'dead': n}``."""
    now = now or timezone.now()
    batch_size = batch_size or _setting('OUTBOX_BATCH_SIZE', 200)
    stats = {'processed': 0, 'failed': 0, 'dead': 0}

    if not settings.NEO4J_ENABLED:
        # No graph to project into: events are recorded (so tests and audits see them) and
        # marked done. Reconciliation rebuilds the graph if it's switched on later.
        ids = list(OutboxEvent.objects.pending().order_by('id').values_list('id', flat=True)[:batch_size])
        stats['processed'] = OutboxEvent.objects.filter(id__in=ids).update(processed_at=now)
        return stats

    if graph is None:
        from .graph import get_graph
        graph = get_graph()

    with transaction.atomic():
        events = list(
            OutboxEvent.objects.pending().filter(next_attempt_at__lte=now)
            .select_for_update(skip_locked=True).order_by('id')[:batch_size]
        )
        touched = []
        for event in events:
            touched.append(event)
            handler = HANDLERS.get(event.kind)
            if handler is None or not isinstance(event.payload, dict):
                event.dead_at = now
                event.last_error = f'Unknown event kind or bad payload: {event.kind}'[:1000]
                stats['dead'] += 1
                continue
            try:
                handler(graph, **event.payload)
            except Exception as exc:
                _fail(event, exc, now)
                stats['dead' if event.dead_at else 'failed'] += 1
                if _is_connection_error(exc):
                    break
                continue
            event.attempts += 1
            event.processed_at = now
            event.last_error = ''
            stats['processed'] += 1
        if touched:
            OutboxEvent.objects.bulk_update(touched, UPDATE_FIELDS)
    return stats


def purge_processed(older_than_days=None):
    days = older_than_days or _setting('OUTBOX_RETENTION_DAYS', 7)
    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = OutboxEvent.objects.filter(processed_at__lt=cutoff).delete()
    return deleted


def requeue_dead(ids=None):
    """Give dead-lettered events another full set of attempts (after fixing the cause)."""
    qs = OutboxEvent.objects.dead()
    if ids is not None:
        qs = qs.filter(id__in=ids)
    return qs.update(dead_at=None, attempts=0, next_attempt_at=timezone.now(), last_error='')
