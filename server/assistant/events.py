"""Run progress pushed to the owner's notification socket (``assistant_event`` handler)."""
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def push(run, event, **extra):
    """Send a small progress event. The consumer forwards only whitelisted keys; never fails the caller."""
    payload = {'event': event, 'run_id': run.id, 'status': run.status, **extra}
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(f'notifications_{run.owner_id}', {'type': 'assistant_event',
                                                                          'payload': payload})
    except Exception:
        logger.warning('Assistant event push failed for run %s', run.id, exc_info=True)
