"""
Asynchronous moderation of new and edited content.

Content is published immediately and checked within seconds. Clear
violations are hidden; uncertain cases stay visible and wait in the staff
review queue. The AI service owns the models; this module owns the policy
mapping and the audit trail.
"""
import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core import ai_client
from .models import STATUS_OK, STATUS_REMOVED, STATUS_REVIEW, ModerationCase

logger = logging.getLogger(__name__)

STATUS_FOR = {'allow': STATUS_OK, 'review': STATUS_REVIEW, 'remove': STATUS_REMOVED}


def _load(content_type, object_id):
    from .targets import load
    return load(content_type, object_id)


def queue_moderation(content_type, object_id):
    if not (settings.AI_MODERATION_ENABLED and ai_client.enabled()):
        return
    transaction.on_commit(lambda: moderate_content.delay(content_type, object_id))


@shared_task(name='moderation.tasks.moderate_content', queue='default',
             autoretry_for=(ai_client.AIUnavailable,), retry_backoff=True, retry_backoff_max=600, max_retries=6)
def moderate_content(content_type, object_id):
    obj, author, text = _load(content_type, object_id)
    if obj is None or author is None:
        return
    age_days = (timezone.now() - author.date_joined).days
    result = ai_client.call('/v1/moderate', {
        'content_type': content_type, 'text': text[:20_000], 'account_age_days': max(age_days, 0),
    }, user_id=author.id)

    decision = result['decision']
    with transaction.atomic():
        case = ModerationCase.objects.create(
            content_type=content_type, object_id=object_id, author=author, decision=decision,
            categories=result.get('categories', []), confidence=result.get('confidence', 0),
            reason=result.get('reason', '')[:300], model=result.get('model') or '',
            stages=result.get('stages', []), degraded=result.get('degraded', False),
            cost_usd=result.get('cost_usd', 0), resolved=decision == 'allow', snapshot=text[:4000],
        )
        from .targets import set_status
        set_status(content_type, obj, STATUS_FOR[decision])

    if decision == 'remove':
        _notify_author(author, content_type, object_id, case.pk)


def _notify_author(author, content_type, object_id, case_id=None):
    try:
        from notifications.models import Notification
        from notifications.service import notify
        notify(author, Notification.TYPE_SYSTEM,
               f'Your {content_type} was removed for breaking the community guidelines. '
               'A moderator will review it if you appeal.',
               extra={'kind': 'moderation', 'content_type': content_type, 'object_id': object_id,
                      'case_id': case_id})
    except Exception:
        logger.warning('Could not notify author about removal', exc_info=True)
