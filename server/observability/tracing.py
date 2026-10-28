"""
OpenTelemetry tracing for Django, Celery, Channels (WebSockets) and outbound
calls to the AI service. Off unless ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set;
the standard ``OTEL_*`` variables (service name, sampler, headers) apply.

Spans carry routes and paths, never query strings (search terms, WebSocket
tickets), headers or bodies.
"""
import logging
import os
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

_enabled = False
EXCLUDED_URLS = 'api/health,metrics'
_URL_ATTRS = ('http.url', 'url.full')
_TARGET_ATTRS = ('http.target',)


def enabled():
    return _enabled


def _scrub(span, path):
    if not span or not span.is_recording():
        return
    for attr in _TARGET_ATTRS:
        span.set_attribute(attr, path)
    span.set_attribute('url.path', path)
    span.set_attribute('url.query', '')
    for attr in _URL_ATTRS:
        span.set_attribute(attr, path)


def _django_request_hook(span, request):
    _scrub(span, request.path)


def _asgi_hook(span, scope):
    _scrub(span, scope.get('path', ''))


def _urllib3_request_hook(span, pool, request_info):
    if span and span.is_recording() and request_info is not None:
        parts = urlsplit(request_info.url)
        span.set_attribute('http.url', f'{parts.scheme}://{parts.netloc}{parts.path}')
        span.set_attribute('url.full', f'{parts.scheme}://{parts.netloc}{parts.path}')


def setup(service_name='andromeda-api'):
    """Install the tracer provider and instrumentations once per process."""
    global _enabled
    if _enabled or not os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT'):
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.celery import CeleryInstrumentor
        from opentelemetry.instrumentation.django import DjangoInstrumentor
        from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning('OTEL_EXPORTER_OTLP_ENDPOINT is set but OpenTelemetry is not installed')
        return False

    resource = Resource.create({'service.name': os.environ.get('OTEL_SERVICE_NAME', service_name)})
    provider = TracerProvider(resource=resource)  # sampler from OTEL_TRACES_SAMPLER(_ARG)
    # BatchSpanProcessor re-creates its worker thread after fork, so prefork Celery children are fine.
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    DjangoInstrumentor().instrument(request_hook=_django_request_hook, excluded_urls=EXCLUDED_URLS)
    CeleryInstrumentor().instrument()
    URLLib3Instrumentor().instrument(request_hook=_urllib3_request_hook)
    _enabled = True
    return True


def wrap_websockets(app):
    """Trace WebSocket connections (Channels). HTTP is traced by the Django instrumentation."""
    if not _enabled:
        return app
    from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware

    return OpenTelemetryMiddleware(app, server_request_hook=_asgi_hook, excluded_urls=EXCLUDED_URLS)
