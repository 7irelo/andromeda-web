import json
import logging

import pytest
from django.test import Client
from django.urls import reverse

from core import ai_client
from observability import errors, logs, metrics, request_id, tracing, views


@pytest.fixture
def client(db):
    return Client()


class TestRequestId:
    def test_generated_when_missing(self, client):
        resp = client.get('/api/health/')
        rid = resp.headers['X-Request-ID']
        assert len(rid) == 32 and int(rid, 16) >= 0

    def test_sane_inbound_id_is_kept(self, client):
        resp = client.get('/api/health/', HTTP_X_REQUEST_ID='4f3c2b1a0e9d8c7b6a5f4e3d2c1b0a99')
        assert resp.headers['X-Request-ID'] == '4f3c2b1a0e9d8c7b6a5f4e3d2c1b0a99'

    @pytest.mark.parametrize('bad', ['short', 'has space in it', 'line\nbreak-injected', 'x' * 200, '<script>x'])
    def test_unsafe_inbound_id_is_replaced(self, client, bad):
        resp = client.get('/api/health/', HTTP_X_REQUEST_ID=bad)
        assert resp.headers['X-Request-ID'] != bad and len(resp.headers['X-Request-ID']) == 32

    def test_context_is_cleared_after_the_request(self, client):
        client.get('/api/health/')
        assert request_id.get() is None

    def test_log_records_carry_the_id(self):
        record = logging.LogRecord('x', logging.INFO, __file__, 1, 'hello %s', ('world',), None)
        token = request_id.set('abcdef0123456789')
        try:
            request_id.RequestIdFilter().filter(record)
        finally:
            request_id.reset(token)
        out = json.loads(logs.JsonFormatter().format(record))
        assert out['msg'] == 'hello world' and out['request_id'] == 'abcdef0123456789' and out['level'] == 'INFO'

    def test_celery_publish_adds_the_header(self):
        headers = {}
        token = request_id.set('abcdef0123456789')
        try:
            request_id._on_publish(headers=headers)
        finally:
            request_id.reset(token)
        assert headers == {request_id.CELERY_HEADER: 'abcdef0123456789'}

    def test_celery_worker_adopts_the_header(self):
        class Req:
            andromeda_request_id = 'feedface00112233'

        class Task:
            request = Req()

        task = Task()
        request_id._on_prerun(task=task)
        assert request_id.get() == 'feedface00112233'
        request_id._on_postrun(task=task)
        assert request_id.get() is None

    def test_ai_calls_carry_the_id(self, settings, monkeypatch):
        settings.AI_SERVICE_URL = 'http://ai:8100'
        settings.AI_SERVICE_SECRET = 's' * 40
        seen = {}

        class Resp:
            status = 200
            data = b'{}'

        def fake_request(method, url, body, headers):
            seen.update(headers)
            return Resp()

        monkeypatch.setattr(ai_client._http, 'request', fake_request)
        token = request_id.set('abcdef0123456789')
        try:
            ai_client.call('/v1/moderate', {}, user_id=1)
        finally:
            request_id.reset(token)
        assert seen['X-Request-ID'] == 'abcdef0123456789'


class TestSentryScrubbing:
    def test_strips_credentials_cookies_bodies_and_queries(self):
        event = {
            'request': {
                'url': 'https://x.test/api/search/?q=secret',
                'headers': {'Authorization': 'Bearer abc', 'Cookie': 'andromeda_refresh=1', 'User-Agent': 'ua'},
                'cookies': {'andromeda_refresh': '1'}, 'data': {'password': 'hunter2'}, 'query_string': 'q=secret',
            },
            'user': {'email': 'a@b.c'},
            'breadcrumbs': {'values': [{'data': {'url': 'http://ai:8100/v1/x?token=1'}}]},
        }
        out = errors.scrub_event(event)
        assert out['request']['headers'] == {'Authorization': '[Filtered]', 'Cookie': '[Filtered]', 'User-Agent': 'ua'}
        assert 'cookies' not in out['request'] and 'data' not in out['request']
        assert 'query_string' not in out['request'] and out['request']['url'] == 'https://x.test/api/search/'
        assert 'user' not in out
        assert out['breadcrumbs']['values'][0]['data']['url'] == 'http://ai:8100/v1/x'

    def test_off_without_a_dsn(self, monkeypatch):
        monkeypatch.delenv('SENTRY_DSN', raising=False)
        assert errors.setup() is False

    def test_init_collects_nothing_identifying(self, monkeypatch):
        import sentry_sdk
        seen = {}
        monkeypatch.setenv('SENTRY_DSN', 'https://key@o1.ingest.example.invalid/1')
        monkeypatch.setattr(errors, '_enabled', False)
        monkeypatch.setattr(sentry_sdk, 'init', lambda **kw: seen.update(kw))
        assert errors.setup() is True
        dc = seen['data_collection']
        assert dc['user_info'] is False and dc['http_bodies'] == [] and dc['stack_frame_variables'] is False
        assert dc['cookies'] == dc['url_query_params'] == {'mode': 'off'}
        assert seen['include_local_variables'] is False and seen['before_send'] is errors.scrub_event
        assert not seen.get('send_default_pii')


class TestErrorTunnel:
    DSN = 'https://publickey@o1.ingest.example.io/12345'

    def _post(self, client, body):
        return client.post(reverse('error-tunnel'), data=body, content_type='text/plain;charset=UTF-8')

    def test_disabled_without_a_frontend_dsn(self, client, settings):
        settings.SENTRY_FRONTEND_DSN = ''
        assert self._post(client, b'{}\n').status_code == 404

    def test_relays_only_our_dsn_to_its_own_host(self, client, settings, monkeypatch):
        settings.SENTRY_FRONTEND_DSN = self.DSN
        sent = []
        monkeypatch.setattr(views._http, 'request', lambda method, url, body, headers: sent.append(url))
        envelope = json.dumps({'dsn': self.DSN}).encode() + b'\n{"type":"event"}\n{}'
        assert self._post(client, envelope).status_code == 204
        assert sent == ['https://o1.ingest.example.io/api/12345/envelope/']

        other = json.dumps({'dsn': 'https://k@evil.example/1'}).encode() + b'\n{}'
        assert self._post(client, other).status_code == 400
        assert self._post(client, b'not json').status_code == 400
        assert self._post(client, b'x' * (views.MAX_ENVELOPE_BYTES + 1)).status_code == 413
        assert len(sent) == 1


class TestMetricsAndTracing:
    @pytest.mark.parametrize('code,reason', [(1000, 'normal'), (1001, 'normal'), (1006, 'abnormal'),
                                             (4003, 'policy'), (1011, 'error'), (None, 'error')])
    def test_disconnect_reasons(self, code, reason):
        assert metrics.disconnect_reason(code) == reason

    def test_tracing_is_off_without_an_endpoint(self, monkeypatch):
        monkeypatch.delenv('OTEL_EXPORTER_OTLP_ENDPOINT', raising=False)
        assert tracing.setup() is False
        app = object()
        assert tracing.wrap_websockets(app) is app

    def test_span_urls_lose_their_query_strings(self):
        attrs = {}

        class Span:
            def is_recording(self):
                return True

            def set_attribute(self, key, value):
                attrs[key] = value

        tracing._asgi_hook(Span(), {'path': '/ws/chat/1/', 'query_string': b'ticket=secret'})
        assert 'secret' not in json.dumps(attrs) and attrs['url.path'] == '/ws/chat/1/'
