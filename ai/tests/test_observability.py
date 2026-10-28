import asyncio
import json
import logging

import pytest
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel

from app.budget import Budget
from app.gateway import Gateway, ProviderError, Route, Usage, prompt_hash
from app.observability import JsonFormatter, RequestIdFilter, scrub_event

SECRET = 'test-secret-for-the-ai-service-0123456789'
PROMPT = 'Summarise: my bank PIN is 4321'

_exporter = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(_exporter))
trace.set_tracer_provider(_provider)


class Out(BaseModel):
    answer: str


class Provider:
    def __init__(self, name, fail=False):
        self.name, self.fail = name, fail

    async def structured(self, route, system, user, schema):
        if self.fail:
            raise ProviderError(f'upstream said: {user}')  # provider errors can echo the prompt
        return Out(answer='the reply text'), Usage(1200, 300)

    async def embed(self, route, texts):
        return [[0.1] * 4 for _ in texts], Usage(50, 0)


ROUTES = {'catchup.summarise': [Route('anthropic', 'claude-haiku-5-5', 4096), Route('openai', 'gpt-6.1-terra', 4096)],
          'search.embed': [Route('openai', 'text-embedding-3-small', 0, None)]}


@pytest.fixture(autouse=True)
def spans():
    _exporter.clear()
    yield _exporter
    _exporter.clear()


def _gateway(**providers):
    return Gateway(providers=providers, budget=Budget(1_000_000), routes=ROUTES, prompt_hash_key=b'k' * 32)


def test_model_call_span_uses_genai_conventions(spans):
    gw = _gateway(anthropic=Provider('anthropic'))
    asyncio.run(gw.structured('catchup.summarise', system='sys', user=PROMPT, schema=Out, user_id=7))

    (span,) = spans.get_finished_spans()
    a = dict(span.attributes)
    assert span.name == 'chat claude-haiku-5-5'
    assert a['gen_ai.system'] == 'anthropic' and a['gen_ai.request.model'] == 'claude-haiku-5-5'
    assert a['gen_ai.operation.name'] == 'chat' and a['gen_ai.request.max_tokens'] == 4096
    assert a['gen_ai.usage.input_tokens'] == 1200 and a['gen_ai.usage.output_tokens'] == 300
    assert a['ai.job'] == 'catchup.summarise' and a['ai.outcome'] == 'ok'
    assert a['ai.cost_usd'] == pytest.approx((1200 * 0.10 + 300 * 0.50) / 1_000_000)
    assert a['ai.prompt_hash'] == prompt_hash(b'k' * 32, 'sys', PROMPT) and len(a['ai.prompt_hash']) == 32


def test_spans_never_contain_prompt_or_response_text(spans):
    gw = _gateway(anthropic=Provider('anthropic', fail=True), openai=Provider('openai'))
    asyncio.run(gw.structured('catchup.summarise', system='sys', user=PROMPT, schema=Out, user_id=7))
    asyncio.run(gw.embed('search.embed', texts=[PROMPT], user_id=7))

    finished = spans.get_finished_spans()
    assert [s.attributes['ai.outcome'] for s in finished] == ['error', 'ok', 'ok']
    assert finished[0].attributes['error.type'] == 'ProviderError'
    dump = json.dumps([{**dict(s.attributes), 'status': s.status.description, 'name': s.name,
                        'events': [dict(e.attributes or {}) for e in s.events]} for s in finished])
    assert 'PIN' not in dump and '4321' not in dump and 'the reply text' not in dump


def test_prompt_hash_is_keyed():
    assert prompt_hash(b'a', 'x') != prompt_hash(b'b', 'x')
    assert prompt_hash(b'a', 'x') == prompt_hash(b'a', 'x')


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('AI_SERVICE_SECRET', SECRET)
    from app.config import get_settings
    get_settings.cache_clear()
    from app.main import app
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_request_id_is_adopted_or_generated(client):
    assert client.get('/healthz', headers={'X-Request-ID': 'abcdef0123456789'}).headers['x-request-id'] == \
        'abcdef0123456789'
    replaced = client.get('/healthz', headers={'X-Request-ID': 'bad id\r\nX-Evil: 1'}).headers['x-request-id']
    assert replaced != 'bad id' and len(replaced) == 32


def test_json_logs_carry_the_request_id():
    record = logging.LogRecord('app', logging.WARNING, __file__, 1, 'route failed', (), None)
    RequestIdFilter().filter(record)
    out = json.loads(JsonFormatter().format(record))
    assert out['msg'] == 'route failed' and out['request_id'] == '-' and out['service'] == 'andromeda-ai'


def test_sentry_events_are_scrubbed():
    event = scrub_event({'request': {'url': 'http://ai/v1/ask?q=x', 'headers': {'Authorization': 'Bearer t'},
                                     'data': {'question': 'secret'}}, 'user': {'id': '42'}})
    assert event == {'request': {'url': 'http://ai/v1/ask'}}
