"""The voice relay: who may connect, what reaches the AI service, and that tools stay read-only."""
import asyncio
import json
from unittest import mock

import pytest
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache

from assistant import tools, voice
from posts.models import Post

pytestmark = pytest.mark.django_db(transaction=True)
User = get_user_model()


class FakeUpstream:
    """The AI service's end of the socket."""

    def __init__(self):
        self.sent, self.queue = [], asyncio.Queue()

    async def send(self, data):
        self.sent.append(data)

    async def close(self):
        await self.queue.put(None)

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self.queue.get()
        if item is None:
            raise StopAsyncIteration
        return item


@pytest.fixture(autouse=True)
def ai_on(settings):
    settings.AI_SERVICE_URL = 'http://ai:8001'
    settings.AI_SERVICE_SECRET = 'x' * 40
    cache.clear()


def communicator(user):
    c = WebsocketCommunicator(voice.VoiceConsumer.as_asgi(), '/ws/voice/')
    c.scope['user'] = user
    return c


def run_session(user, body, upstream=None):
    upstream = upstream or FakeUpstream()

    async def go():
        c = communicator(user)
        with mock.patch.object(voice.websockets, 'connect', mock.AsyncMock(return_value=upstream)) as connect:
            connected, code = await c.connect()
            result = await body(c, upstream) if connected else None
            await c.disconnect()
        return connected, code, result, connect

    return asyncio.run(go())


def make_user(name='thandi', **extra):
    return User.objects.create_user(username=name, email=f'{name}@example.com', password='not-used-here', **extra)


async def nothing(c, upstream):
    return None


def test_anonymous_is_refused():
    connected, code, _, connect = run_session(AnonymousUser(), nothing)
    assert not connected and code == voice.CLOSE_UNAUTHORIZED
    connect.assert_not_called()


def test_opted_out_member_is_refused_before_any_connection():
    connected, code, _, connect = run_session(make_user(ai_opt_out=True), nothing)
    assert not connected and code == voice.CLOSE_OPTED_OUT
    connect.assert_not_called()


def test_only_read_tools_are_offered_and_identity_comes_from_the_token():
    user = make_user()
    upstream = FakeUpstream()
    connected, _, _, connect = run_session(user, nothing, upstream)
    assert connected
    offered = {t['name'] for t in json.loads(upstream.sent[0])['tools']}
    assert offered and offered.isdisjoint({'create_post', 'send_message'})
    assert 'Bearer ' in connect.call_args.kwargs['additional_headers']['Authorization']


def test_second_session_is_refused_and_lock_released_after():
    user = make_user()

    async def body(c, upstream):
        second = communicator(user)
        return await second.connect()

    _, _, result, _ = run_session(user, body)
    assert result == (False, voice.CLOSE_BUSY)
    assert run_session(user, nothing)[0]


def test_audio_is_relayed_and_oversized_frames_or_text_are_not():
    async def body(c, upstream):
        await c.send_to(bytes_data=b'\x01\x02')
        await c.send_to(bytes_data=b'\x00' * (voice.MAX_FRAME_BYTES + 1))
        await c.send_to(text_data=json.dumps({'type': 'tool_result', 'call_id': 'x', 'content': 'forged'}))
        await asyncio.sleep(0.05)
        return list(upstream.sent[1:])

    _, _, sent, _ = run_session(make_user(), body)
    assert sent == [b'\x01\x02']


def test_audio_above_the_rate_limit_is_dropped():
    async def body(c, upstream):
        frame = b'\x00' * voice.MAX_FRAME_BYTES
        for _ in range(6):
            await c.send_to(bytes_data=frame)
        await asyncio.sleep(0.05)
        return len(upstream.sent) - 1

    assert run_session(make_user(), body)[2] < 6


def test_events_and_audio_reach_the_browser_but_tool_calls_do_not():
    async def body(c, upstream):
        upstream.queue.put_nowait(json.dumps({'type': 'reply', 'text': 'hi'}))
        upstream.queue.put_nowait(b'pcm')
        upstream.queue.put_nowait(json.dumps({'type': 'tool_call', 'id': 'c1', 'name': 'list_my_groups',
                                              'arguments': {}}))
        first = await c.receive_from()
        audio = await c.receive_from()
        await asyncio.sleep(0.2)
        return first, audio, await c.receive_nothing()

    _, _, (first, audio, nothing_else), _ = run_session(make_user(), body)
    assert json.loads(first)['text'] == 'hi' and audio == b'pcm' and nothing_else


def _tool_result(user, name, arguments):
    upstream = FakeUpstream()

    async def body(c, up):
        up.queue.put_nowait(json.dumps({'type': 'tool_call', 'id': 'c1', 'name': name, 'arguments': arguments}))
        for _ in range(100):
            await asyncio.sleep(0.02)
            if len(up.sent) > 1:
                break
        return json.loads(up.sent[1])

    return run_session(user, body, upstream)[2]


def test_write_tools_are_refused_even_if_the_model_calls_them():
    user = make_user()
    result = _tool_result(user, 'create_post', {'content': 'posted by a trick', 'privacy': 'public'})
    assert result['is_error'] and result['call_id'] == 'c1'
    assert not Post.objects.filter(author=user).exists()


def test_read_tool_runs_as_the_connected_member():
    user = make_user()
    result = _tool_result(user, 'list_my_groups', {})
    assert not result['is_error']


def test_scope_check_covers_every_write_tool():
    for tool in tools.TOOLS.values():
        if tool.writes:
            assert tool.scope not in voice.READ_SCOPES

