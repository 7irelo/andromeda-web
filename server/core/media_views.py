"""Serving public media from storage, and daily scheduled work, for deployments without nginx or Celery Beat."""
import mimetypes
import secrets
from datetime import UTC, datetime

from celery import current_app
from celery.schedules import crontab
from django.conf import settings
from django.core.files.storage import default_storage
from django.http import Http404, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET

# Same restrictions nginx applies to /media/public/: an uploaded file can never run as a page.
MEDIA_CSP = "default-src 'none'; img-src 'self'; media-src 'self'; sandbox"


@require_GET
def public_media(request, path):
    if not path.startswith('public/') or '..' in path.split('/'):
        raise Http404
    try:
        fh = default_storage.open(path, 'rb')
    except (FileNotFoundError, ValueError):
        raise Http404 from None
    response = HttpResponse(fh.read(), content_type=mimetypes.guess_type(path)[0] or 'application/octet-stream')
    # Names are random and never reused, so the CDN can keep these and spare the function.
    response['Cache-Control'] = 'public, max-age=3600, s-maxage=86400'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = MEDIA_CSP
    return response


def due_today(schedule, now):
    """Whether a Beat entry should run on ``now``'s date. Anything shorter than a day runs once daily here."""
    if not isinstance(schedule, crontab):
        return True
    return (now.isoweekday() % 7 in schedule.day_of_week
            and now.day in schedule.day_of_month
            and now.month in schedule.month_of_year)


@require_GET
def run_scheduled_tasks(request):
    """Vercel Cron's replacement for Celery Beat. The free plan allows one run a day."""
    secret = getattr(settings, 'CRON_SECRET', '')
    if not secret:
        raise Http404
    if not secrets.compare_digest(request.headers.get('Authorization', ''), f'Bearer {secret}'):
        return JsonResponse({'detail': 'Unauthorized'}, status=401)
    now = datetime.now(UTC)
    sent = []
    for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
        if due_today(entry['schedule'], now):
            current_app.send_task(entry['task'], args=entry.get('args', ()), kwargs=entry.get('kwargs', {}))
            sent.append(name)
    return JsonResponse({'sent': sent})
