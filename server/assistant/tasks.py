"""
Assistant runs execute on the dedicated 'ai' queue, so a slow or failing
model provider can only back up assistant work, never notifications, chat or
email.
"""
import datetime as dt
import logging

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from core import ai_client

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def dispatch(run_id):
    try:
        execute_run.apply_async(args=[run_id], queue='ai')
    except Exception:
        logger.warning('Could not queue assistant run %s', run_id, exc_info=True)


@shared_task(bind=True, name='assistant.tasks.execute_run', queue='ai', acks_late=True,
             max_retries=MAX_RETRIES, ignore_result=True)
def execute_run(self, run_id):
    """Advance one run. A redelivered or retried task resumes from the last recorded step."""
    from . import runner
    from .models import AssistantRun

    if not runner.claim(run_id):
        return
    run = AssistantRun.objects.select_related('owner').get(pk=run_id)
    try:
        runner.advance(run)
    except ai_client.AIUnavailable as exc:
        runner.release(run_id)
        if self.request.retries < MAX_RETRIES:
            raise self.retry(exc=exc, countdown=5 * 2 ** self.request.retries) from None
        runner.fail(run, 'The assistant is unavailable right now. Try again in a few minutes.')
    except Exception:
        logger.exception('Assistant run %s failed', run_id)
        runner.fail(run, 'Something went wrong.')
    finally:
        runner.release(run_id)


STUCK_AFTER = dt.timedelta(minutes=10)


@shared_task(name='assistant.tasks.housekeeping', queue='ai', ignore_result=True)
def housekeeping():
    expired = expire_proposals()
    return expired, requeue_stuck_runs()


def requeue_stuck_runs():
    """Runs whose task was lost (a worker died, a retry was never delivered) are queued again."""
    from .models import AssistantRun

    now = timezone.now()
    stuck = AssistantRun.objects.filter(
        status__in=[AssistantRun.STATUS_QUEUED, AssistantRun.STATUS_RUNNING], updated_at__lt=now - STUCK_AFTER,
    ).filter(Q(locked_until__isnull=True) | Q(locked_until__lt=now)).values_list('id', flat=True)[:200]
    ids = list(stuck)
    for run_id in ids:
        dispatch(run_id)
    return len(ids)


def expire_proposals():
    """Expire proposals nobody decided on, and let their runs finish."""
    from . import runner
    from .models import Proposal

    stale = Proposal.objects.filter(status=Proposal.STATUS_PENDING, expires_at__lte=timezone.now()).select_related('run')
    count = 0
    for proposal in stale[:500]:
        runner.expire(proposal)
        count += 1
        if proposal.run_id:
            proposal.run.refresh_from_db()
            runner.resume(proposal.run)
    return count
