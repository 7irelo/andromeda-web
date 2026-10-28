from celery import shared_task

from . import drain as _drain
from . import reconcile as _reconcile


@shared_task(name='outbox.tasks.drain_outbox', queue='default', ignore_result=True)
def drain_outbox(max_batches=10):
    """Beat, every few seconds: apply due events, a few batches per tick so a backlog clears quickly."""
    total = {'processed': 0, 'failed': 0, 'dead': 0}
    for _ in range(max_batches):
        stats = _drain.drain()
        for k, v in stats.items():
            total[k] += v
        if stats['processed'] + stats['failed'] + stats['dead'] == 0 or stats['failed']:
            break
    return total


@shared_task(name='outbox.tasks.reconcile_graph', queue='default', soft_time_limit=55 * 60, time_limit=60 * 60)
def reconcile_graph():
    from django.conf import settings

    if not settings.NEO4J_ENABLED:
        return {}
    return _reconcile.reconcile()


@shared_task(name='outbox.tasks.purge_processed', queue='default')
def purge_processed():
    return _drain.purge_processed()
