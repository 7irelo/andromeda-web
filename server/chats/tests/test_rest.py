"""REST chat endpoints: tombstones, catch-up, unread counts, search and group management."""
import io
from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.urls import reverse
from PIL import Image

from chats.models import ChatMember, ChatRoom, Message
from chats.tests.helpers import client_for, make_room, make_user
from chats.views import _search
from users.models import Block

pytestmark = pytest.mark.django_db


@pytest.fixture
def alice(db):
    return make_user('alice')


@pytest.fixture
def bob(db):
    return make_user('bob')


@pytest.fixture
def carol(db):
    return make_user('carol')


@pytest.fixture
def mallory(db):
    return make_user('mallory')


@pytest.fixture
def group(alice, bob, carol):
    return make_room(alice, bob, carol)


def url(name, room, **extra):
    return reverse(f'chatroom-{name}', kwargs={'pk': room.pk, **extra})


def png(color='red'):
    buf = io.BytesIO()
    Image.new('RGB', (8, 8), color).save(buf, format='PNG')
    return SimpleUploadedFile('a.png', buf.getvalue(), content_type='image/png')


class TestMessageList:
    def test_tombstones_are_listed(self, group, alice, bob):
        Message.objects.create(room=group, sender=alice, content='gone', is_deleted=True)
        Message.objects.create(room=group, sender=bob, content='here')
        results = client_for(bob).get(url('messages', group)).data['results']
        assert [m['is_deleted'] for m in results] == [False, True]
        assert results[1]['content'] == ''

    def test_after_id_returns_newer_oldest_first(self, group, alice):
        msgs = [Message.objects.create(room=group, sender=alice, content=str(i)) for i in range(5)]
        r = client_for(alice).get(url('messages', group) + f'?after_id={msgs[1].id}')
        assert [m['content'] for m in r.data['results']] == ['2', '3', '4']
        assert r.data['has_more'] is False

    def test_after_id_validated_and_member_only(self, group, alice, mallory):
        assert client_for(alice).get(url('messages', group) + '?after_id=abc').status_code == 400
        assert client_for(mallory).get(url('messages', group) + '?after_id=0').status_code == 404

    def test_reply_data_for_deleted_parent(self, group, alice, bob):
        parent = Message.objects.create(room=group, sender=alice, content='secret', is_deleted=True)
        Message.objects.create(room=group, sender=bob, content='re', reply_to=parent)
        reply = client_for(bob).get(url('messages', group)).data['results'][0]
        assert reply['reply_to_data']['is_deleted'] and reply['reply_to_data']['content'] == ''

    def test_rest_reply_must_be_same_room(self, group, alice, mallory):
        foreign = Message.objects.create(room=make_room(mallory), sender=mallory, content='x')
        r = client_for(alice).post(reverse('message-list'), {'room': group.id, 'content': 'hi',
                                                             'reply_to': foreign.id})
        assert r.status_code == 400

    def test_rest_edit_and_delete(self, group, alice, bob):
        msg = Message.objects.create(room=group, sender=alice, content='v1')
        detail = reverse('message-detail', kwargs={'pk': msg.pk})
        r = client_for(alice).patch(detail, {'content': 'v2'}, format='json')
        assert r.status_code == 200 and r.data['edited_at'] and r.data['is_edited']
        assert client_for(bob).delete(detail).status_code == 403
        assert client_for(alice).delete(detail).status_code == 204
        msg.refresh_from_db()
        assert msg.is_deleted and msg.content == ''


class TestUnread:
    def test_counts_exclude_own_and_read(self, group, alice, bob):
        Message.objects.create(room=group, sender=alice, content='mine')
        for i in range(3):
            Message.objects.create(room=group, sender=bob, content=str(i))
        other = make_room(bob, alice)
        Message.objects.create(room=other, sender=bob, content='x')
        c = client_for(alice)
        data = c.get(reverse('chatroom-unread')).data
        assert data['total'] == 4 and data['rooms_with_unread'] == 2
        assert data['rooms'][group.id] == 3
        c.post(url('mark-read', group))
        assert c.get(reverse('chatroom-unread')).data['total'] == 1
        rooms = {r['id']: r['unread_count'] for r in c.get(reverse('chatroom-list')).data['results']}
        assert rooms == {group.id: 0, other.id: 1}

    def test_room_list_has_no_n_plus_one(self, alice, bob, carol, django_assert_max_num_queries):
        def make(n):
            for _ in range(n):
                room = make_room(bob, alice, carol)
                Message.objects.create(room=room, sender=bob, content='hello')

        make(2)
        c = client_for(alice)
        from django.db import connection as conn
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(conn) as small:
            c.get(reverse('chatroom-list'))
        make(8)
        with django_assert_max_num_queries(len(small.captured_queries)):
            r = c.get(reverse('chatroom-list'))
        assert len(r.data['results']) == 10
        assert all(room['last_message']['content'] == 'hello' for room in r.data['results'])

    def test_unread_is_per_user(self, group, alice, mallory):
        Message.objects.create(room=group, sender=alice, content='x')
        assert client_for(mallory).get(reverse('chatroom-unread')).data['total'] == 0


class TestSearch:
    def test_finds_text_and_transcripts(self, group, alice, bob):
        Message.objects.create(room=group, sender=alice, content='Pizza on Friday?')
        Message.objects.create(room=group, sender=bob, message_type='voice', transcript='pizza sounds great',
                               transcript_status='done')
        Message.objects.create(room=group, sender=bob, content='unrelated')
        r = client_for(alice).get(url('search', group) + '?q=pizza')
        assert r.status_code == 200 and len(r.data['results']) == 2

    def test_members_only(self, group, alice, mallory):
        Message.objects.create(room=group, sender=alice, content='pizza')
        assert client_for(mallory).get(url('search', group) + '?q=pizza').status_code == 404

    def test_removed_member_cannot_search(self, group, alice, bob):
        Message.objects.create(room=group, sender=alice, content='pizza')
        ChatMember.objects.filter(room=group, user=bob).delete()
        assert client_for(bob).get(url('search', group) + '?q=pizza').status_code == 404

    def test_excludes_deleted_and_blocked(self, group, alice, bob, carol):
        Message.objects.create(room=group, sender=alice, content='pizza', is_deleted=True)
        Message.objects.create(room=group, sender=carol, content='pizza from carol')
        Block.objects.create(blocker=carol, blocked=bob)
        assert client_for(bob).get(url('search', group) + '?q=pizza').data['results'] == []

    def test_query_length(self, group, alice):
        c = client_for(alice)
        assert c.get(url('search', group) + '?q=a').status_code == 400
        assert c.get(url('search', group) + '?q=' + 'a' * 101).status_code == 400

    def test_postgres_filters_on_match_not_rank(self, group):
        with mock.patch.object(connection, 'vendor', 'postgresql'):
            sql = str(_search(Message.objects.filter(room=group), 'pizza').query)
        assert '@@' in sql and 'ts_rank' in sql
        assert '"_rank" >' not in sql and 'ts_rank(' not in sql.split('WHERE', 1)[1].split('ORDER BY')[0]


class TestGroupManagement:
    def test_rename_admin_only(self, group, alice, bob, mallory):
        assert client_for(bob).patch(url('rename', group), {'name': 'Mine'}, format='json').status_code == 403
        assert client_for(mallory).patch(url('rename', group), {'name': 'Mine'}, format='json').status_code == 404
        assert client_for(alice).patch(url('rename', group), {'name': '  '}, format='json').status_code == 400
        r = client_for(alice).patch(url('rename', group), {'name': 'Hikers'}, format='json')
        assert r.status_code == 200 and r.data['name'] == 'Hikers'

    def test_avatar_admin_only_and_sanitized(self, group, alice, bob):
        assert client_for(bob).post(url('avatar', group), {'avatar': png()}, format='multipart').status_code == 403
        bad = SimpleUploadedFile('a.png', b'<svg onload=alert(1)>', content_type='image/png')
        assert client_for(alice).post(url('avatar', group), {'avatar': bad}, format='multipart').status_code == 400
        r = client_for(alice).post(url('avatar', group), {'avatar': png()}, format='multipart')
        assert r.status_code == 200
        group.refresh_from_db()
        assert group.avatar.name.startswith('public/chat_avatars/') and group.avatar.name.endswith('.png')
        assert 'a.png' not in group.avatar.name
        assert client_for(alice).delete(url('avatar', group)).status_code == 200
        group.refresh_from_db()
        assert not group.avatar

    def test_dm_cannot_be_managed(self, alice, bob):
        dm = make_room(alice, bob, room_type='direct')
        c = client_for(alice)
        assert c.patch(url('rename', dm), {'name': 'x'}, format='json').status_code == 400
        assert c.post(url('remove-member', dm), {'user_id': bob.id}).status_code == 400
        assert c.post(url('set-role', dm), {'user_id': bob.id, 'role': 'admin'}).status_code == 400
        assert c.post(url('avatar', dm), {'avatar': png()}, format='multipart').status_code == 400

    def test_add_member_admin_only_and_respects_blocks(self, group, alice, bob, mallory):
        assert client_for(bob).post(url('add-member', group), {'user_id': mallory.id}).status_code == 403
        Block.objects.create(blocker=mallory, blocked=alice)
        assert client_for(alice).post(url('add-member', group), {'user_id': mallory.id}).status_code == 403
        Block.objects.all().delete()
        assert client_for(alice).post(url('add-member', group), {'user_id': mallory.id}).status_code == 200
        assert ChatMember.objects.filter(room=group, user=mallory).exists()

    def test_remove_member(self, group, alice, bob, carol):
        assert client_for(bob).post(url('remove-member', group), {'user_id': carol.id}).status_code == 403
        assert client_for(alice).post(url('remove-member', group), {'user_id': alice.id}).status_code == 400
        assert client_for(alice).post(url('remove-member', group), {'user_id': 999}).status_code == 404
        assert client_for(alice).post(url('remove-member', group), {'user_id': carol.id}).status_code == 200
        # Removed members lose access to everything in the room.
        c = client_for(carol)
        assert c.get(url('messages', group)).status_code == 404
        assert c.post(reverse('message-list'), {'room': group.id, 'content': 'hi'}).status_code == 403

    def test_set_role(self, group, alice, bob):
        assert client_for(bob).post(url('set-role', group), {'user_id': bob.id, 'role': 'admin'}).status_code == 403
        assert client_for(alice).post(url('set-role', group), {'user_id': bob.id, 'role': 'owner'}).status_code == 400
        assert client_for(alice).post(url('set-role', group), {'user_id': bob.id, 'role': 'admin'}).status_code == 200
        assert ChatMember.objects.get(room=group, user=bob).role == 'admin'
        # Bob, now an admin, can manage.
        assert client_for(bob).patch(url('rename', group), {'name': 'Bob rules'}, format='json').status_code == 200

    def test_last_admin_cannot_demote_self(self, group, alice):
        r = client_for(alice).post(url('set-role', group), {'user_id': alice.id, 'role': 'member'})
        assert r.status_code == 400
        assert ChatMember.objects.get(room=group, user=alice).role == 'admin'

    def test_last_admin_leaving_promotes_longest_member(self, group, alice, bob):
        assert client_for(alice).post(url('leave', group)).status_code == 200
        assert ChatMember.objects.get(room=group, user=bob).role == 'admin'
        assert not ChatMember.objects.filter(room=group, user=alice).exists()

    def test_member_can_leave_and_last_member_deletes_room(self, alice, bob):
        room = make_room(alice, bob)
        assert client_for(bob).post(url('leave', room)).status_code == 200
        assert client_for(alice).post(url('leave', room)).status_code == 200
        assert not ChatRoom.objects.filter(pk=room.pk).exists()

    def test_room_exposes_my_role(self, group, alice, bob):
        assert client_for(alice).get(reverse('chatroom-detail', kwargs={'pk': group.pk})).data['my_role'] == 'admin'
        assert client_for(bob).get(reverse('chatroom-detail', kwargs={'pk': group.pk})).data['my_role'] == 'member'
