"""Compose assist ("help me write"): authorization, validation and AI error mapping."""
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from core import ai_client
from posts.models import Post

URL = '/api/posts/compose-assist/'


@pytest.fixture(autouse=True)
def _clear_throttles():
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def alice(db):
    return get_user_model().objects.create_user(username='alice', email='alice@example.com',
                                                password='correct-horse-battery')


@pytest.fixture
def ai_on(settings):
    settings.AI_SERVICE_URL = 'http://ai.internal'
    settings.AI_SERVICE_SECRET = 's' * 40


def client_for(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def ai_rewrite(text='Hello friends!'):
    return mock.patch('core.ai_client.call', return_value={'text': text, 'model': 'claude-haiku-5-5',
                                                            'cost_usd': 0.0001, 'truncated': False,
                                                            'removed_contacts': 0})


def test_route_is_under_posts():
    assert reverse('post-compose-assist') == URL


def test_rewrites_without_saving_anything(alice, ai_on):
    with ai_rewrite() as call:
        r = client_for(alice).post(URL, {'text': ' hello frends ', 'action': 'grammar', 'language': 'zu'},
                                   format='json')
    assert r.status_code == 200 and r.data == {'text': 'Hello friends!', 'truncated': False}
    path, payload = call.call_args.args
    assert path == '/v1/compose' and call.call_args.kwargs['user_id'] == alice.id
    # Language only travels with a translation; the draft is trimmed.
    assert payload == {'text': 'hello frends', 'action': 'grammar', 'language': None, 'kind': 'post'}
    assert not Post.objects.exists()


def test_translate_and_listing_kind(alice, ai_on):
    with ai_rewrite('Sawubona') as call:
        r = client_for(alice).post(URL, {'text': 'Hello', 'action': 'translate', 'language': 'zu',
                                         'kind': 'listing'}, format='json')
    assert r.status_code == 200
    assert call.call_args.args[1] == {'text': 'Hello', 'action': 'translate', 'language': 'zu', 'kind': 'listing'}


def test_anonymous_is_rejected(db, ai_on):
    with ai_rewrite() as call:
        assert APIClient().post(URL, {'text': 'x', 'action': 'grammar'}, format='json').status_code == 401
    call.assert_not_called()


def test_opt_out_is_respected(alice, ai_on):
    alice.ai_opt_out = True
    alice.save(update_fields=['ai_opt_out'])
    with ai_rewrite() as call:
        assert client_for(alice).post(URL, {'text': 'x', 'action': 'grammar'}, format='json').status_code == 403
    call.assert_not_called()


@pytest.mark.parametrize('body', [
    {'text': '', 'action': 'grammar'}, {'text': '   ', 'action': 'grammar'}, {'text': 'x' * 5001, 'action': 'grammar'},
    {'text': 'x', 'action': 'shout'}, {'text': 'x', 'action': 'translate'},
    {'text': 'x', 'action': 'translate', 'language': 'fr'}, {'text': 'x', 'action': 'grammar', 'kind': 'comment'},
    {'action': 'grammar'},
])
def test_validates_input(alice, ai_on, body):
    with ai_rewrite() as call:
        assert client_for(alice).post(URL, body, format='json').status_code == 400
    call.assert_not_called()


def test_ai_errors_are_mapped(alice, ai_on):
    c = client_for(alice)
    body = {'text': 'x', 'action': 'shorter'}
    with mock.patch('core.ai_client.call', side_effect=ai_client.AIUnavailable('down')):
        assert c.post(URL, body, format='json').status_code == 503
    with mock.patch('core.ai_client.call', side_effect=ai_client.AIRejected(429, 'Daily AI allowance used up')):
        r = c.post(URL, body, format='json')
        assert r.status_code == 429 and 'allowance' in r.data['detail']
    with mock.patch('core.ai_client.call', side_effect=ai_client.AIRejected(422, 'The model declined')):
        assert c.post(URL, body, format='json').status_code == 422


def test_unconfigured_ai_is_a_friendly_503(alice):
    r = client_for(alice).post(URL, {'text': 'x', 'action': 'shorter'}, format='json')
    assert r.status_code == 503 and 'not available' in r.data['detail']


def test_uses_the_ai_throttle_scope(alice, ai_on):
    rates = {**ScopedRateThrottle.THROTTLE_RATES, 'ai': '1/min'}
    c = client_for(alice)
    with mock.patch.object(ScopedRateThrottle, 'THROTTLE_RATES', rates), ai_rewrite():
        assert c.post(URL, {'text': 'x', 'action': 'shorter'}, format='json').status_code == 200
        assert c.post(URL, {'text': 'x', 'action': 'shorter'}, format='json').status_code == 429
        # The rest of the posts API doesn't share the AI allowance.
        assert c.get('/api/posts/').status_code == 200
