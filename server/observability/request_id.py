"""
Request ids: one id per request, in the response, in every log line, in the
Celery tasks it queues and in calls to the AI service.

nginx generates the id (``$request_id``) and passes it as ``X-Request-ID``.
An inbound id is only trusted if it looks like an id (short, no spaces or
control characters, so it can't forge log lines); anything else is replaced
with a fresh one.
"""
import contextvars
import logging
import re
import uuid

from asgiref.sync import iscoroutinefunction, markcoroutinefunction

HEADER = 'X-Request-ID'
META_KEY = 'HTTP_X_REQUEST_ID'
CELERY_HEADER = 'andromeda_request_id'
_VALID = re.compile(r'^[A-Za-z0-9._:-]{8,128}$')

_current = contextvars.ContextVar('request_id', default=None)


def new_id():
    return uuid.uuid4().hex


def clean(value):
    """``value`` if it's an acceptable id, else None."""
    if isinstance(value, bytes):
        value = value.decode('latin-1', 'replace')
    return value if isinstance(value, str) and _VALID.match(value) else None


def get():
    return _current.get()


def set(value):  # noqa: A001 - mirrors ContextVar.set
    return _current.set(value)


def reset(token):
    _current.reset(token)


class RequestIdMiddleware:
    """Sets the request id for the request's context and echoes it in the response."""

    sync_capable = True
    async_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        if iscoroutinefunction(get_response):
            markcoroutinefunction(self)

    def _start(self, request):
        rid = clean(request.META.get(META_KEY)) or new_id()
        request.request_id = rid
        return rid, _current.set(rid)

    def __call__(self, request):
        if iscoroutinefunction(self):
            return self.__acall__(request)
        rid, token = self._start(request)
        try:
            response = self.get_response(request)
        finally:
            _current.reset(token)
        response[HEADER] = rid
        return response

    async def __acall__(self, request):
        rid, token = self._start(request)
        try:
            response = await self.get_response(request)
        finally:
            _current.reset(token)
        response[HEADER] = rid
        return response


class RequestIdFilter(logging.Filter):
    """Adds ``request_id`` (or "-") to every record so formatters can rely on it."""

    def filter(self, record):
        if not getattr(record, 'request_id', None):
            record.request_id = _current.get() or '-'
        return True


# ── Celery ───────────────────────────────────────────────────────────────────

def _on_publish(headers=None, **kwargs):
    rid = _current.get()
    if rid and headers is not None and CELERY_HEADER not in headers:
        headers[CELERY_HEADER] = rid


def _on_prerun(task=None, **kwargs):
    if task is None:
        return
    rid = clean(getattr(task.request, CELERY_HEADER, None))
    # Eager tasks (tests) run inside the caller's context and keep its id.
    task.request._andromeda_rid_token = _current.set(rid or _current.get() or new_id())


def _on_postrun(task=None, **kwargs):
    token = getattr(getattr(task, 'request', None), '_andromeda_rid_token', None)
    if token is not None:
        try:
            _current.reset(token)
        except ValueError:  # set in another context (eager tasks inside a request)
            _current.set(None)


def connect_celery():
    from celery import signals

    signals.before_task_publish.connect(_on_publish, weak=False, dispatch_uid='andromeda-rid-publish')
    signals.task_prerun.connect(_on_prerun, weak=False, dispatch_uid='andromeda-rid-prerun')
    signals.task_postrun.connect(_on_postrun, weak=False, dispatch_uid='andromeda-rid-postrun')
