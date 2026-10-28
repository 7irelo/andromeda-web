"""
Sentry error reporting. Off unless ``SENTRY_DSN`` is set.

Nothing identifying leaves the server: automatic data collection is off
(``DATA_COLLECTION``: the sentry-sdk 2.7x replacement for
``send_default_pii=False``, which it deprecates, and stricter: no user info,
cookies, headers, bodies, query params, SQL parameters, task arguments or
local variables), and every event has its auth headers, cookies, query string
and body stripped again before it is sent.
"""
import os

SENSITIVE_HEADERS = {'authorization', 'cookie', 'set-cookie', 'x-csrftoken', 'x-api-key', 'proxy-authorization'}
_enabled = False
_OFF = {'mode': 'off'}
DATA_COLLECTION = {
    'user_info': False, 'cookies': _OFF, 'http_headers': {'request': _OFF}, 'http_bodies': [],
    'url_query_params': _OFF, 'graphql': {'document': False, 'variables': False},
    'gen_ai': {'inputs': False, 'outputs': False}, 'database_query_data': False, 'queues': False,
    'stack_frame_variables': False,
}


def scrub_event(event, hint=None):
    request = event.get('request')
    if isinstance(request, dict):
        headers = request.get('headers')
        if isinstance(headers, dict):
            request['headers'] = {k: ('[Filtered]' if k.lower() in SENSITIVE_HEADERS else v)
                                  for k, v in headers.items()}
        for key in ('cookies', 'data', 'query_string', 'env'):
            request.pop(key, None)
        if isinstance(request.get('url'), str):
            request['url'] = request['url'].split('?', 1)[0]
    event.pop('user', None)
    crumbs = event.get('breadcrumbs')
    values = crumbs.get('values', []) if isinstance(crumbs, dict) else crumbs if isinstance(crumbs, list) else []
    for crumb in values:
        data = crumb.get('data') if isinstance(crumb, dict) else None
        if isinstance(data, dict):
            for key in ('url', 'http.query'):
                if isinstance(data.get(key), str):
                    data[key] = data[key].split('?', 1)[0]
    return event


def setup():
    global _enabled
    dsn = os.environ.get('SENTRY_DSN', '')
    if _enabled or not dsn:
        return False
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get('SENTRY_ENVIRONMENT', 'production'),
        release=os.environ.get('SENTRY_RELEASE') or None,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        data_collection=DATA_COLLECTION,
        include_local_variables=False,
        max_request_body_size='never',
        traces_sample_rate=float(os.environ.get('SENTRY_TRACES_SAMPLE_RATE', '0')),
        before_send=scrub_event,
        before_send_transaction=scrub_event,
    )
    _enabled = True
    return True
