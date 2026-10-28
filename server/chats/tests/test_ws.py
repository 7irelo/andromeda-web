"""
WebSocket chat consumer: membership on connect and on every frame, edits,
deletes, reactions, presence and blocks. A failure here is a security bug.
"""
import pytest
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.urls import reverse

from chats import consumers
from chats.models import ChatMember, Message, MessageReaction
from chats.tests.helpers import WS, client_for, make_room, make_user
from users.models import Block

pytestmark = pytest.mark.django_db


def run(coro_fn):
    async_to_sync(coro_fn)()


@pytest.fixture
def alice(db):
    return make_user('alice')


@pytest.fixture
def bob(db):
    return make_user('bob')


@pytest.fixture
def mallory(db):
    return make_user('mallory')


@pytest.fixture
def group(alice, bob):
    return make_room(alice, bob)


@pytest.fixture
def dm(alice, bob):
    return make_room(alice, bob, room_type='direct')


def db(fn, *args, **kwargs):
    return database_sync_to_async(fn)(*args, **kwargs)


def with_commits(fn):
    """Run a REST call with its on_commit hooks (broadcasts, kicks) executed."""
    def inner():
        with TestCase.captureOnCommitCallbacks(execute=True):
            return fn()
    return database_sync_to_async(inner)()


class TestConnect:
    def test_anonymous_rejected(self, group):
        async def go():
            ok, code = await WS(AnonymousUser(), group.id).connect()
            assert not ok and code == 4001
        run(go)

    def test_non_member_rejected(self, group, mallory):
        async def go():
            ok, code = await WS(mallory, group.id).connect()
            assert not ok and code == 4003
        run(go)

    def test_member_gets_presence_snapshot(self, group, alice):
        async def go():
            ws = WS(alice, group.id)
            assert (await ws.connect())[0]
            frame = await ws.receive()
            assert frame == {'type': 'presence', 'online': []}
            await ws.close()
        run(go)


class TestMessages:
    def test_message_broadcast_with_sender(self, group, alice, bob):
        async def go():
            a, b = WS(alice, group.id), WS(bob, group.id)
            await a.connect()
            await b.connect()
            await a.drain()
            await b.drain()
            await a.send({'type': 'message', 'content': 'hello'})
            frame = await b.receive_type('message')
            assert frame['message']['content'] == 'hello'
            assert frame['message']['sender']['username'] == 'alice'
            assert 'email' not in frame['message']['sender']
            await a.close()
            await b.close()
        run(go)

    def test_reply_to_other_room_is_dropped(self, group, alice, mallory):
        other = make_room(mallory)
        foreign = Message.objects.create(room=other, sender=mallory, content='elsewhere')

        async def go():
            a = WS(alice, group.id)
            await a.connect()
            await a.send({'type': 'message', 'content': 'hi', 'reply_to': foreign.id})
            frame = await a.receive_type('message')
            assert frame['message']['reply_to'] is None
            await a.close()
        run(go)

    def test_reply_in_same_room_carries_quote(self, group, alice, bob):
        parent = Message.objects.create(room=group, sender=bob, content='question?')

        async def go():
            a = WS(alice, group.id)
            await a.connect()
            await a.send({'type': 'message', 'content': 'answer', 'reply_to': parent.id})
            frame = await a.receive_type('message')
            assert frame['message']['reply_to_data']['content'] == 'question?'
            assert frame['message']['reply_to_data']['sender'] == 'bob'
            await a.close()
        run(go)

    def test_oversized_frame_closes(self, group, alice):
        async def go():
            a = WS(alice, group.id)
            await a.connect()
            await a.drain()
            await a.send('x' * (consumers.MAX_FRAME_BYTES + 1))
            assert (await a.receive())['code'] == 4009
        run(go)

    def test_rate_limited(self, group, alice):
        async def go():
            a = WS(alice, group.id)
            await a.connect()
            for _ in range(consumers.BURST + 2):
                await a.send({'type': 'typing', 'is_typing': True})
            assert (await a.receive_type('error'))['code'] == 'rate_limited'
            await a.close()
        run(go)

    def test_read_moves_marker_forward(self, group, alice, bob):
        msg = Message.objects.create(room=group, sender=bob, content='x')

        async def go():
            a = WS(alice, group.id)
            await a.connect()
            await a.send({'type': 'read', 'message_id': msg.id})
            assert (await a.receive_type('read'))['message_id'] == msg.id
            await a.close()
        run(go)
        assert ChatMember.objects.get(room=group, user=alice).last_read_at == msg.created_at


class TestEditDelete:
    def test_author_edits_and_room_sees_it(self, group, alice, bob):
        msg = Message.objects.create(room=group, sender=alice, content='teh typo')

        async def go():
            a, b = WS(alice, group.id), WS(bob, group.id)
            await a.connect()
            await b.connect()
            await a.send({'type': 'edit', 'message_id': msg.id, 'content': 'the typo'})
            frame = await b.receive_type('message_updated')
            assert frame['message']['content'] == 'the typo'
            assert frame['message']['is_edited'] and frame['message']['edited_at']
            await a.close()
            await b.close()
        run(go)
        msg.refresh_from_db()
        assert msg.content == 'the typo' and msg.edited_at is not None

    def test_cannot_edit_or_delete_others_message(self, group, alice, bob):
        msg = Message.objects.create(room=group, sender=alice, content='mine')

        async def go():
            b = WS(bob, group.id)
            await b.connect()
            await b.send({'type': 'edit', 'message_id': msg.id, 'content': 'pwned'})
            assert (await b.receive_type('error'))['code'] == 'forbidden'
            await b.send({'type': 'delete', 'message_id': msg.id})
            assert (await b.receive_type('error'))['code'] == 'forbidden'
            await b.close()
        run(go)
        msg.refresh_from_db()
        assert msg.content == 'mine' and not msg.is_deleted

    def test_cannot_touch_message_in_another_room(self, group, alice):
        # Alice is the author, but the message lives in a room this socket isn't for.
        other = make_room(alice)
        msg = Message.objects.create(room=other, sender=alice, content='elsewhere')

        async def go():
            a = WS(alice, group.id)
            await a.connect()
            await a.send({'type': 'edit', 'message_id': msg.id, 'content': 'x'})
            assert (await a.receive_type('error'))['code'] == 'not_found'
            await a.send({'type': 'react', 'message_id': msg.id, 'reaction': 'like'})
            assert (await a.receive_type('error'))['code'] == 'not_found'
            await a.close()
        run(go)
        msg.refresh_from_db()
        assert msg.content == 'elsewhere' and not msg.reactions.exists()

    def test_delete_leaves_tombstone(self, group, alice, bob):
        msg = Message.objects.create(room=group, sender=alice, content='oops')
        MessageReaction.objects.create(message=msg, user=bob, reaction='haha')

        async def go():
            a, b = WS(alice, group.id), WS(bob, group.id)
            await a.connect()
            await b.connect()
            await a.send({'type': 'delete', 'message_id': msg.id})
            frame = await b.receive_type('message_updated')
            assert frame['message']['is_deleted'] and frame['message']['content'] == ''
            await a.close()
            await b.close()
        run(go)
        msg.refresh_from_db()
        assert msg.is_deleted and msg.content == '' and not msg.reactions.exists()

    def test_edit_in_dm_after_block_refused(self, dm, alice, bob):
        msg = Message.objects.create(room=dm, sender=alice, content='hi')
        Block.objects.create(blocker=bob, blocked=alice)

        async def go():
            a = WS(alice, dm.id)
            await a.connect()
            await a.send({'type': 'edit', 'message_id': msg.id, 'content': 'still here'})
            assert (await a.receive_type('error'))['code'] == 'forbidden'
            await a.close()
        run(go)


class TestReactions:
    def test_one_reaction_per_user(self, group, alice, bob):
        msg = Message.objects.create(room=group, sender=alice, content='nice')

        async def go():
            a, b = WS(alice, group.id), WS(bob, group.id)
            await a.connect()
            await b.connect()
            await b.send({'type': 'react', 'message_id': msg.id, 'reaction': 'like'})
            frame = await a.receive_type('reaction')
            assert frame['reactions'] == [{'reaction': 'like', 'count': 1}] and frame['user_id'] == bob.id
            await b.send({'type': 'react', 'message_id': msg.id, 'reaction': 'love'})
            frame = await a.receive_type('reaction')
            assert frame['reactions'] == [{'reaction': 'love', 'count': 1}]
            await b.send({'type': 'react', 'message_id': msg.id, 'reaction': None})
            frame = await a.receive_type('reaction')
            assert frame['reactions'] == [] and frame['reaction'] is None
            await a.close()
            await b.close()
        run(go)
        assert not msg.reactions.exists()

    def test_unknown_reaction_rejected(self, group, alice):
        msg = Message.objects.create(room=group, sender=alice, content='x')

        async def go():
            a = WS(alice, group.id)
            await a.connect()
            await a.send({'type': 'react', 'message_id': msg.id, 'reaction': '<script>'})
            assert (await a.receive_type('error'))['code'] == 'bad_request'
            await a.close()
        run(go)
        assert not msg.reactions.exists()

    def test_cannot_react_to_deleted(self, group, alice, bob):
        msg = Message.objects.create(room=group, sender=alice, content='', is_deleted=True)

        async def go():
            b = WS(bob, group.id)
            await b.connect()
            await b.send({'type': 'react', 'message_id': msg.id, 'reaction': 'like'})
            assert (await b.receive_type('error'))['code'] == 'not_found'
            await b.close()
        run(go)

    def test_blocked_in_dm_cannot_react(self, dm, alice, bob):
        msg = Message.objects.create(room=dm, sender=alice, content='x')
        Block.objects.create(blocker=alice, blocked=bob)

        async def go():
            b = WS(bob, dm.id)
            await b.connect()
            await b.send({'type': 'react', 'message_id': msg.id, 'reaction': 'like'})
            assert (await b.receive_type('error'))['code'] == 'forbidden'
            await b.close()
        run(go)
        assert not msg.reactions.exists()


class TestRemovedMembers:
    def test_removed_member_socket_closes_on_next_frame(self, group, bob):
        async def go():
            b = WS(bob, group.id)
            await b.connect()
            await db(ChatMember.objects.filter(room=group, user=bob).delete)
            await b.drain()
            for frame in ({'type': 'message', 'content': 'still here?'},):
                await b.send(frame)
            assert (await b.receive_type('__closed__'))['code'] == 4003
        run(go)
        assert not group.messages.exists()

    def test_removed_member_is_kicked_and_stops_receiving(self, group, alice, bob):
        async def go():
            a, b = WS(alice, group.id), WS(bob, group.id)
            await a.connect()
            await b.connect()
            await b.drain()
            r = await with_commits(lambda: client_for(alice).post(
                reverse('chatroom-remove-member', kwargs={'pk': group.pk}), {'user_id': bob.id}))
            assert r.status_code == 200
            frame = await b.receive_type('__closed__')
            assert frame['code'] == 4003
            await a.send({'type': 'message', 'content': 'after removal'})
            assert (await a.receive_type('message'))['message']['content'] == 'after removal'
            await a.close()
        run(go)

    def test_leaving_closes_own_socket(self, group, bob):
        async def go():
            b = WS(bob, group.id)
            await b.connect()
            r = await with_commits(lambda: client_for(bob).post(reverse('chatroom-leave', kwargs={'pk': group.pk})))
            assert r.status_code == 200
            assert (await b.receive_type('__closed__'))['code'] == 4003
        run(go)


class TestPresence:
    def test_status_broadcast_to_room(self, group, alice, bob):
        async def go():
            a = WS(alice, group.id)
            await a.connect()
            await a.drain()
            b = WS(bob, group.id)
            await b.connect()
            frame = await a.receive_type('status')
            assert frame['user_id'] == bob.id and frame['status'] == 'online'
            assert (await b.receive_type('presence'))['online'] == [alice.id]
            await b.close()
            assert (await a.receive_type('status'))['status'] == 'offline'
            await a.close()
        run(go)

    def test_hidden_status_not_broadcast(self, group, alice, bob):
        bob.show_online_status = False
        bob.save()

        async def go():
            a = WS(alice, group.id)
            await a.connect()
            await a.drain()
            b = WS(bob, group.id)
            await b.connect()
            assert await a.nothing()
            r = await db(lambda: client_for(alice).get(reverse('chatroom-presence', kwargs={'pk': group.pk})))
            assert r.data == {'online': []}
            await b.close()
            await a.close()
        run(go)

    def test_blocked_users_see_no_status_or_typing(self, group, alice, bob):
        Block.objects.create(blocker=alice, blocked=bob)

        async def go():
            a = WS(alice, group.id)
            await a.connect()
            await a.drain()
            b = WS(bob, group.id)
            await b.connect()
            assert (await b.receive_type('presence'))['online'] == []
            await b.send({'type': 'typing', 'is_typing': True})
            assert await a.nothing()
            r = await db(lambda: client_for(bob).get(reverse('chatroom-presence', kwargs={'pk': group.pk})))
            assert r.data == {'online': []}
            await b.close()
            await a.close()
        run(go)
