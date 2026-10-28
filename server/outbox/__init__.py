"""
Transactional outbox.

Side effects that leave Postgres (today: the Neo4j projection) are recorded as
``OutboxEvent`` rows by the same database connection that makes the change, so
they commit or roll back with it. ``outbox.tasks.drain_outbox`` (Celery beat,
every few seconds) applies them in id order with idempotent handlers, retries
with exponential backoff and jitter, and dead-letters an event after
``OUTBOX_MAX_ATTEMPTS``. A nightly reconciliation compares Postgres with the
graph and repairs whatever drifted anyway.
"""


def emit(kind, **payload):
    """Record one event in the current transaction. ``payload`` must be JSON-serialisable."""
    from .handlers import HANDLERS
    from .models import OutboxEvent

    if kind not in HANDLERS:
        raise ValueError(f'Unknown outbox event kind: {kind}')
    return OutboxEvent.objects.create(kind=kind, payload=payload)
