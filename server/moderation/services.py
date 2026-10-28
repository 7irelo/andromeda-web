"""
Moderation actions, reports and appeals.

Every human decision is written to the append-only ModerationAction log.
Account actions (warn, suspend, ban) always come with a notice to the member,
and removals can be appealed once, to a person.
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from .models import STATUS_OK, STATUS_REMOVED, Appeal, ModerationAction, ModerationCase, Report
from . import targets

MAX_SUSPENSION_DAYS = 90


def _notify(user, title, **extra):
    from notifications.models import Notification
    from notifications.service import notify
    notify(user, Notification.TYPE_SYSTEM, title, extra={'kind': 'moderation', **extra})


def file_report(reporter, content_type, object_id, reason, details=''):
    obj, author, text = targets.load(content_type, object_id)
    if obj is None or not targets.can_see(reporter, content_type, obj):
        raise NotFound('That content is not available.')
    if author is not None and author.pk == reporter.pk:
        raise ValidationError({'detail': "You can't report your own content."})
    with transaction.atomic():
        case = (ModerationCase.objects.select_for_update()
                .filter(content_type=content_type, object_id=object_id, resolved=False).first())
        if case is None:
            case = ModerationCase.objects.create(
                content_type=content_type, object_id=object_id, author=author, decision='review',
                source=ModerationCase.SOURCE_REPORT, reason=f'Reported: {reason}', snapshot=text[:targets.SNAPSHOT_CHARS])
        report, created = Report.objects.get_or_create(
            reporter=reporter, content_type=content_type, object_id=object_id,
            defaults={'reason': reason, 'details': details[:1000], 'case': case})
        if not created:
            raise ValidationError({'detail': 'You already reported this. Thanks, we have it.'})
        ModerationCase.objects.filter(pk=case.pk).update(report_count=F('report_count') + 1)
    return report


def _log(case, moderator, action, note=''):
    return ModerationAction.objects.create(case=case, moderator=moderator, action=action, note=note[:500])


def _close(case, outcome):
    case.resolved = True
    case.save(update_fields=['resolved'])
    reports = list(case.reports.filter(status=Report.STATUS_OPEN).select_related('reporter'))
    Report.objects.filter(pk__in=[r.pk for r in reports]).update(status=outcome)
    for r in reports:
        # Reporters hear that it was looked at, never what happened to whom.
        _notify(r.reporter, 'Thanks for your report. Our team reviewed it.', case_id=case.pk)


def resolve(case, moderator, action, note='', days=None):
    """Apply a moderator's decision to a case."""
    obj, author, _ = targets.load(case.content_type, case.object_id)
    if obj is None and action not in ('dismiss', 'approve'):
        raise ValidationError({'detail': 'The content no longer exists.'})
    if author is not None and author.pk == moderator.pk:
        raise PermissionDenied('You cannot moderate your own content or account.')
    if author is not None and (author.is_staff or author.is_superuser) and action in ('suspend', 'ban') \
            and not moderator.is_superuser:
        raise PermissionDenied('Only a superuser can suspend or ban staff.')

    with transaction.atomic():
        _log(case, moderator, action, note)
        if action == 'approve':
            if obj is not None:
                targets.set_status(case.content_type, obj, STATUS_OK)
            _close(case, Report.STATUS_DISMISSED)
        elif action == 'dismiss':
            _close(case, Report.STATUS_DISMISSED)
        elif action == 'remove':
            targets.set_status(case.content_type, obj, STATUS_REMOVED)
            _close(case, Report.STATUS_ACTIONED)
            if author is not None:
                _notify(author, f'Your {case.get_content_type_display().lower()} was removed for breaking the '
                                'community guidelines. You can appeal from your notifications.', case_id=case.pk)
        elif action == 'restore':
            targets.set_status(case.content_type, obj, STATUS_OK)
            _close(case, Report.STATUS_DISMISSED)
        elif action == 'warn':
            _close(case, Report.STATUS_ACTIONED)
            if author is not None:
                _notify(author, 'Warning: something you shared broke the community guidelines. '
                                'Repeated breaks can lead to a suspension.', case_id=case.pk)
        elif action == 'suspend':
            days = int(days or 0)
            if not 1 <= days <= MAX_SUSPENSION_DAYS:
                raise ValidationError({'days': f'Choose 1 to {MAX_SUSPENSION_DAYS} days.'})
            until = timezone.now() + timedelta(days=days)
            type(author).objects.filter(pk=author.pk).update(suspended_until=until)
            _end_sessions(author)
            _close(case, Report.STATUS_ACTIONED)
            _notify(author, f'Your account is suspended for {days} day{"s" if days != 1 else ""} for breaking '
                            'the community guidelines.', case_id=case.pk)
        elif action == 'ban':
            type(author).objects.filter(pk=author.pk).update(is_active=False)
            _end_sessions(author)
            _close(case, Report.STATUS_ACTIONED)
        else:
            raise ValidationError({'action': 'Unknown action.'})
    return case


def _end_sessions(user):
    from users.views import _revoke_all_sessions
    _revoke_all_sessions(user)


def appeal(author, case, message=''):
    if case.author_id != author.pk:
        raise NotFound()
    removed = case.decision == 'remove' or case.actions.filter(action='remove').exists()
    if not removed:
        raise ValidationError({'detail': 'Only removals can be appealed.'})
    if Appeal.objects.filter(case=case).exists():
        raise ValidationError({'detail': 'You already appealed this decision.'})
    with transaction.atomic():
        a = Appeal.objects.create(case=case, author=author, message=message[:1000])
        case.resolved = False
        case.save(update_fields=['resolved'])
    return a


def decide_appeal(appeal_obj, moderator, restore, note=''):
    case = appeal_obj.case
    if appeal_obj.status != Appeal.STATUS_OPEN:
        raise ValidationError({'detail': 'This appeal was already decided.'})
    obj, _, _ = targets.load(case.content_type, case.object_id)
    with transaction.atomic():
        if restore and obj is not None:
            targets.set_status(case.content_type, obj, STATUS_OK)
        _log(case, moderator, 'restore' if restore else 'uphold', note)
        appeal_obj.status = Appeal.STATUS_RESTORED if restore else Appeal.STATUS_UPHELD
        appeal_obj.decided_by = moderator
        appeal_obj.decided_at = timezone.now()
        appeal_obj.save(update_fields=['status', 'decided_by', 'decided_at'])
        case.resolved = True
        case.save(update_fields=['resolved'])
    _notify(appeal_obj.author, 'Your appeal was accepted and your content is back.' if restore else
            'We looked at your appeal again and the removal stands.', case_id=case.pk)
    return appeal_obj
