"""
Fixtures for the assistant tests.

``ScriptedAI`` replaces ``core.ai_client.call``: a fake model that routes,
drafts and emits whatever tool calls a test scripts, including malicious
ones. The tool layer has to hold regardless of what it says.
"""
import itertools

import pytest
from django.core.cache import cache

from core import ai_client
from core.test_security import client_for, make_user


@pytest.fixture(autouse=True)
def _clean(settings):
    cache.clear()
    settings.AI_SEARCH_ENABLED = False  # lexical search only: no embedding calls in these tests
    yield
    cache.clear()


def call(name, **arguments):
    return {'name': name, 'arguments': arguments}


class ScriptedAI:
    """
    route: the router's plan. steps: one entry per agent/answer step, each
    {'text': ..., 'calls': [call(...), ...]} or a callable(payload) returning one.
    """

    def __init__(self, route=None, steps=(), draft='', catchup=None, cost=0.001):
        self.plan = {'path': 'agent', 'query': None, 'recipient': None, 'room': None, 'group': None,
                     'reason': '', **(route or {})}
        self.steps = list(steps)
        self.draft = draft
        self.catchup = catchup
        self.cost = cost
        self.calls = []
        self._ids = itertools.count(1)
        self.fail_on = set()

    def paths(self):
        return [p for p, _, _ in self.calls]

    def payloads(self, path):
        return [p for q, p, _ in self.calls if q == path]

    def _meta(self, model):
        return {'model': model, 'cost_usd': self.cost, 'input_tokens': 1000, 'output_tokens': 100,
                'prompt_version': 'abc123def456'}

    def __call__(self, path, payload, user_id):
        self.calls.append((path, payload, user_id))
        if path in self.fail_on:
            raise ai_client.AIUnavailable('down')
        if path == '/v1/assistant/route':
            return {'plan': dict(self.plan), **self._meta('claude-haiku-5-5')}
        if path == '/v1/assistant/draft':
            return {'text': self.draft, **self._meta('claude-sonnet-5-5')}
        if path == '/v1/assistant/step':
            if not self.steps:
                raise AssertionError('The model was called more times than scripted')
            spec = self.steps.pop(0)
            if callable(spec):
                spec = spec(payload)
            calls = [{'id': f'toolu_{next(self._ids)}', **c} for c in spec.get('calls', [])]
            model = 'claude-opus-5-5' if payload['task'] == 'agent' else 'claude-sonnet-5-5'
            native = {'provider': 'anthropic', 'model': model, 'content': [
                {'type': 'thinking', 'thinking': '', 'signature': f'sig-{len(self.calls)}'}] + [
                {'type': 'tool_use', 'id': c['id'], 'name': c['name'], 'input': c['arguments']} for c in calls]}
            return {'text': spec.get('text', ''), 'tool_calls': calls, 'native': native,
                    'stop': 'tool_use' if calls else 'end', 'provider': 'anthropic', 'fallback_used': False,
                    'links_removed': 0, **self._meta(model)}
        if path == '/v1/catchup':
            return {'summary': self.catchup or {'tldr': 'Braai on Saturday.', 'topics': [], 'decisions': [],
                                                'questions_for_you': []}}
        if path == '/v1/moderate':  # posts the assistant publishes are moderated like any other
            return {'decision': 'allow', 'categories': [], 'confidence': 0.99, 'reason': '', 'model': 'fake'}
        raise AssertionError(f'Unexpected AI call {path}')


@pytest.fixture
def fake_ai(monkeypatch):
    def install(**kwargs):
        fake = ScriptedAI(**kwargs)
        monkeypatch.setattr(ai_client, 'enabled', lambda: True)
        monkeypatch.setattr(ai_client, 'call', fake)
        return fake
    return install


@pytest.fixture
def thandi(db):
    return make_user('thandi', first_name='Thandi')


@pytest.fixture
def sipho(db):
    return make_user('sipho', first_name='Sipho')


@pytest.fixture
def mallory(db):
    return make_user('mallory')


@pytest.fixture
def ask(django_capture_on_commit_callbacks):
    """Start a run through the API and let the (eager) Celery task execute it."""
    def _ask(user, text, **extra):
        with django_capture_on_commit_callbacks(execute=True):
            r = client_for(user).post('/api/assistant/runs/', {'request': text, **extra}, format='json')
        assert r.status_code == 202, r.content
        from assistant.models import AssistantRun
        return AssistantRun.objects.get(pk=r.json()['id'])
    return _ask


@pytest.fixture
def decide(django_capture_on_commit_callbacks):
    def _decide(user, proposal, action='approve'):
        with django_capture_on_commit_callbacks(execute=True):
            return client_for(user).post(f'/api/assistant/proposals/{proposal.id}/{action}/')
    return _decide
