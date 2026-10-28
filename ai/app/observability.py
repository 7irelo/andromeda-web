"""
Request ids, JSON logs, tracing and error reporting for the AI service.

- ``X-Request-ID`` from Django is adopted when it looks like an id (else a new
  one is made), echoed in the response and stamped on every log line.
- Tracing is off unless ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set. Model-call
  spans (``app.gateway``) follow the OpenTelemetry GenAI conventions and
  carry token counts, cost and a keyed hash of the prompt, never its text.
- Sentry is off unless ``SENTRY_DSN`` is set; events lose headers, cookies,
  bodies and query strings.
"""
import contextvars
import json
import logging
import os
import re
import uuid
from datetime import UTC, datetime

HEADER = b'x-request-id'
_VALID = re.compile(r'^[A-Za-z0-9._:-]{8,128}$')
_current = contextvars.ContextVar('request_id', default=None)


def current_request_id():
    return _current.get()


def clean(value):
    if isinstance(value, bytes):
        value = value.decode('latin-1', 'replace')
    return value if isinstance(value, str) and _VALID.match(value) else None


class RequestIdMiddleware:
    """Pure ASGI, so it wraps streaming responses too."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        inbound = dict(scope.get('headers') or []).get(HEADER)
        rid = clean(inbound) or uuid.uuid4().hex
        token = _current.set(rid)

        async def send_with_id(message):
            if message['type'] == 'http.response.start':
                headers = [(k, v) for k, v in message.get('headers', []) if k.lower() != HEADER]
                message = {**message, 'headers': headers + [(HEADER, rid.encode())]}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            _current.reset(token)


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        if not getattr(record, 'request_id', None):
            record.request_id = _current.get() or '-'
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record):
        out = {
            'ts': datetime.fromtimestamp(record.created, UTC).isoformat(timespec='milliseconds'),
            'level': record.levelname,
            'logger': record.name,
            'msg': record.getMessage(),
            'request_id': getattr(record, 'request_id', '-'),
            'service': 'andromeda-ai',
        }
        try:
            from opentelemetry import trace
            ctx = trace.get_current_span().get_span_context()
            if ctx.is_valid:
                out['trace_id'], out['span_id'] = f'{ctx.trace_id:032x}', f'{ctx.span_id:016x}'
        except ImportError:
            pass
        if record.exc_info:
            out['exc'] = self.formatException(record.exc_info)
        return json.dumps(out, ensure_ascii=False)


def setup_logging():
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    if os.environ.get('LOG_FORMAT', 'json') == 'json':
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter('%(levelname)s %(name)s [%(request_id)s] %(message)s'))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)


# ── Tracing ──────────────────────────────────────────────────────────────────

def _server_request_hook(span, scope):
    if span and span.is_recording():
        path = scope.get('path', '')
        for attr in ('http.target', 'http.url', 'url.full', 'url.path'):
            span.set_attribute(attr, path)
        span.set_attribute('url.query', '')


def setup_tracing(app):
    if not os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT'):
        return False
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create(
        {'service.name': os.environ.get('OTEL_SERVICE_NAME', 'andromeda-ai')}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, excluded_urls='healthz,metrics',
                                       server_request_hook=_server_request_hook)
    return True


# ── Errors ───────────────────────────────────────────────────────────────────

def scrub_event(event, hint=None):
    request = event.get('request')
    if isinstance(request, dict):
        for key in ('headers', 'cookies', 'data', 'query_string', 'env'):
            request.pop(key, None)
        if isinstance(request.get('url'), str):
            request['url'] = request['url'].split('?', 1)[0]
    event.pop('user', None)
    return event


def setup_errors():
    dsn = os.environ.get('SENTRY_DSN', '')
    if not dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(dsn=dsn, environment=os.environ.get('SENTRY_ENVIRONMENT', 'production'),
                    send_default_pii=False, include_local_variables=False, max_request_body_size='never',
                    traces_sample_rate=0.0, before_send=scrub_event)
    return True
