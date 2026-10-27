"""
Authorization and privacy regression suite.

Each test pins down one "user B must not be able to do X to user A's thing"
rule. A failure here is a security bug, not a flaky test.
"""
import io

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from rest_framework.test import APIClient

from chats.models import ChatMember, ChatRoom, Message
from core import ws_tickets
from groups.models import Group, GroupMember
from marketplace.models import Listing
from pages.models import Page
from posts.models import Post
from users.models import Block, FriendRequest
from watch.models import Video

User = get_user_model()
PASSWORD = 'correct-horse-battery'


def make_user(name, **extra):
    return User.objects.create_user(username=name, email=f'{name}@example.com', password=PASSWORD, **extra)


def client_for(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def befriend(a, b):
    FriendRequest.objects.create(sender=a, receiver=b, status=FriendRequest.STATUS_ACCEPTED)


@pytest.fixture
def alice(db):
    return make_user('alice')


@pytest.fixture
def bob(db):
    return make_user('bob')


@pytest.fixture
def mallory(db):
    return make_user('mallory')


# ── Object ownership ─────────────────────────────────────────────────────────

class TestOwnership:
    def test_stranger_cannot_edit_or_delete_post(self, alice, mallory):
        post = Post.objects.create(author=alice, content='mine')
        c = client_for(mallory)
        url = reverse('post-detail', kwargs={'pk': post.pk})
        assert c.patch(url, {'content': 'pwned'}, format='json').status_code == 403
        assert c.delete(url).status_code == 403
        post.refresh_from_db()
        assert post.content == 'mine'

    def test_put_is_not_allowed(self, alice):
        post = Post.objects.create(author=alice, content='x')
        r = client_for(alice).put(reverse('post-detail', kwargs={'pk': post.pk}), {'content': 'y'})
        assert r.status_code == 405

    def test_stranger_cannot_modify_group(self, alice, mallory):
        group = Group.objects.create(name='Runners', created_by=alice)
        GroupMember.objects.create(group=group, user=alice, role='admin')
        GroupMember.objects.create(group=group, user=mallory, role='member')
        c = client_for(mallory)
        url = reverse('group-detail', kwargs={'pk': group.pk})
        assert c.patch(url, {'name': 'Owned'}, format='json').status_code == 403
        assert c.delete(url).status_code == 403

    def test_stranger_cannot_modify_page(self, alice, mallory):
        page = Page.objects.create(name='Shop', username='shop', created_by=alice)
        c = client_for(mallory)
        url = reverse('page-detail', kwargs={'pk': page.pk})
        assert c.patch(url, {'name': 'Owned'}, format='json').status_code == 403
        assert c.delete(url).status_code == 403

    def test_stranger_cannot_modify_listing(self, alice, mallory):
        listing = Listing.objects.create(seller=alice, title='Couch', price=100)
        c = client_for(mallory)
        url = reverse('listing-detail', kwargs={'pk': listing.pk})
        assert c.patch(url, {'price': 1}, format='json').status_code == 403
        assert c.delete(url).status_code == 403

    def test_stranger_cannot_modify_video(self, alice, mallory):
        video = Video.objects.create(uploader=alice, title='v', video_file='public/x.mp4', status='ready')
        c = client_for(mallory)
        url = reverse('video-detail', kwargs={'pk': video.pk})
        assert c.patch(url, {'title': 'Owned'}, format='json').status_code == 403
        assert c.delete(url).status_code == 403

    def test_cannot_review_own_listing(self, alice):
        listing = Listing.objects.create(seller=alice, title='Couch', price=100)
        r = client_for(alice).post(reverse('listing-reviews', kwargs={'pk': listing.pk}), {'rating': 5})
        assert r.status_code == 403


# ── Post privacy ─────────────────────────────────────────────────────────────

class TestPostVisibility:
    def _ids(self, client, query=''):
        r = client.get(reverse('post-list') + query)
        assert r.status_code == 200
        return {p['id'] for p in r.data['results']}

    def test_private_and_friends_posts_hidden_from_strangers(self, alice, mallory):
        public = Post.objects.create(author=alice, content='hi', privacy='public')
        friends = Post.objects.create(author=alice, content='f', privacy='friends')
        private = Post.objects.create(author=alice, content='p', privacy='private')
        c = client_for(mallory)
        for query in ('', f'?author={alice.id}', '?search=f'):
            ids = self._ids(c, query)
            assert friends.id not in ids and private.id not in ids
        assert public.id in self._ids(c)
        url = reverse('post-detail', kwargs={'pk': private.pk})
        assert c.get(url).status_code == 404

    def test_friends_see_friends_posts_but_not_private(self, alice, bob):
        befriend(alice, bob)
        friends = Post.objects.create(author=alice, content='f', privacy='friends')
        private = Post.objects.create(author=alice, content='p', privacy='private')
        ids = self._ids(client_for(bob))
        assert friends.id in ids and private.id not in ids

    def test_cannot_react_or_comment_on_invisible_post(self, alice, mallory):
        post = Post.objects.create(author=alice, content='p', privacy='private')
        c = client_for(mallory)
        assert c.post(reverse('post-react', kwargs={'pk': post.pk}), {'reaction': 'like'}).status_code == 404
        assert c.post(reverse('post-comments', kwargs={'pk': post.pk}), {'content': 'x'}).status_code == 404

    def test_invalid_reaction_rejected(self, alice):
        post = Post.objects.create(author=alice, content='p')
        r = client_for(alice).post(reverse('post-react', kwargs={'pk': post.pk}), {'reaction': '<script>'})
        assert r.status_code == 400

    def test_cannot_share_friends_only_post(self, alice, bob):
        befriend(alice, bob)
        post = Post.objects.create(author=alice, content='f', privacy='friends')
        r = client_for(bob).post(reverse('post-share', kwargs={'pk': post.pk}))
        assert r.status_code == 403

    def test_cannot_set_shared_post_directly(self, alice, mallory):
        private = Post.objects.create(author=alice, content='secret', privacy='private')
        r = client_for(mallory).post(reverse('post-list'), {'content': 'x', 'shared_post': private.id})
        assert r.status_code == 201
        assert Post.objects.get(pk=r.data['id']).shared_post_id is None

    def test_private_group_posts_hidden_from_non_members(self, alice, mallory):
        group = Group.objects.create(name='Secret club', privacy='private', created_by=alice)
        GroupMember.objects.create(group=group, user=alice, role='admin')
        post = Post.objects.create(author=alice, content='inside', group=group)
        assert post.id not in self._ids(client_for(mallory))

    def test_cannot_post_into_group_without_membership(self, alice, mallory):
        group = Group.objects.create(name='Runners', created_by=alice)
        r = client_for(mallory).post(reverse('post-list'), {'content': 'spam', 'group': group.id})
        assert r.status_code == 400

    def test_cannot_post_as_page_without_role(self, alice, mallory):
        page = Page.objects.create(name='Shop', username='shop', created_by=alice)
        r = client_for(mallory).post(reverse('post-list'), {'content': 'fake', 'page': page.id})
        assert r.status_code == 400

    def test_javascript_links_rejected(self, alice):
        r = client_for(alice).post(reverse('post-list'), {'content': 'x', 'link_url': 'javascript:alert(1)'})
        assert r.status_code == 400


# ── Groups ───────────────────────────────────────────────────────────────────

class TestGroups:
    def test_secret_group_invisible_to_non_members(self, alice, mallory):
        group = Group.objects.create(name='Hidden', privacy='secret', created_by=alice)
        c = client_for(mallory)
        assert c.get(reverse('group-detail', kwargs={'pk': group.pk})).status_code == 404
        assert group.id not in {g['id'] for g in c.get(reverse('group-list')).data['results']}

    def test_private_group_join_creates_request(self, alice, mallory):
        group = Group.objects.create(name='Private', privacy='private', created_by=alice)
        GroupMember.objects.create(group=group, user=alice, role='admin')
        r = client_for(mallory).post(reverse('group-join', kwargs={'pk': group.pk}))
        assert r.data['status'] == 'request_pending'
        assert not group.memberships.filter(user=mallory).exists()
        r = client_for(alice).get(reverse('group-join-requests', kwargs={'pk': group.pk}))
        assert [jr['user']['username'] for jr in r.data] == ['mallory']

    def test_private_group_members_hidden(self, alice, mallory):
        group = Group.objects.create(name='Private', privacy='private', created_by=alice)
        r = client_for(mallory).get(reverse('group-members', kwargs={'pk': group.pk}))
        assert r.status_code == 403

    def test_member_cannot_see_join_requests(self, alice, bob):
        group = Group.objects.create(name='Private', privacy='private', created_by=alice)
        GroupMember.objects.create(group=group, user=bob, role='member')
        assert client_for(bob).get(reverse('group-join-requests', kwargs={'pk': group.pk})).status_code == 403


# ── Chat ─────────────────────────────────────────────────────────────────────

class TestChat:
    @pytest.fixture
    def dm(self, alice, bob):
        room = ChatRoom.objects.create(room_type='direct', created_by=alice)
        ChatMember.objects.create(room=room, user=alice, role='admin')
        ChatMember.objects.create(room=room, user=bob)
        return room

    def test_non_member_cannot_read_messages(self, dm, alice, mallory):
        Message.objects.create(room=dm, sender=alice, content='secret')
        c = client_for(mallory)
        r = c.get(reverse('message-list') + f'?room={dm.id}')
        assert r.status_code in (404, 405)
        assert c.get(reverse('chatroom-messages', kwargs={'pk': dm.pk})).status_code == 404

    def test_non_member_cannot_post_into_room(self, dm, mallory):
        r = client_for(mallory).post(reverse('message-list'), {'room': dm.id, 'content': 'hi'})
        assert r.status_code == 403
        assert not dm.messages.exists()

    def test_cannot_edit_others_message(self, dm, alice, bob):
        msg = Message.objects.create(room=dm, sender=alice, content='original')
        r = client_for(bob).patch(reverse('message-detail', kwargs={'pk': msg.pk}), {'content': 'x'}, format='json')
        assert r.status_code == 403

    def test_cannot_move_message_to_other_room(self, dm, alice, mallory):
        other = ChatRoom.objects.create(room_type='direct', created_by=mallory)
        ChatMember.objects.create(room=other, user=mallory)
        msg = Message.objects.create(room=dm, sender=alice, content='x')
        client_for(alice).patch(reverse('message-detail', kwargs={'pk': msg.pk}), {'room': other.id}, format='json')
        msg.refresh_from_db()
        assert msg.room_id == dm.id

    def test_cannot_add_members_to_dm(self, dm, alice, mallory):
        r = client_for(alice).post(reverse('chatroom-add-member', kwargs={'pk': dm.pk}), {'user_id': mallory.id})
        assert r.status_code == 400

    def test_message_privacy_nobody(self, alice, bob):
        bob.privacy_messages = 'nobody'
        bob.save()
        r = client_for(alice).post(reverse('chatroom-list'), {'member_ids': [bob.id]}, format='json')
        assert r.status_code == 403

    def test_message_privacy_friends(self, alice, bob):
        bob.privacy_messages = 'friends'
        bob.save()
        c = client_for(alice)
        assert c.post(reverse('chatroom-list'), {'member_ids': [bob.id]}, format='json').status_code == 403
        befriend(alice, bob)
        assert c.post(reverse('chatroom-list'), {'member_ids': [bob.id]}, format='json').status_code == 201

    def test_attachment_requires_membership(self, dm, alice, mallory):
        msg = Message.objects.create(
            room=dm, sender=alice, message_type='file',
            file=SimpleUploadedFile('notes.txt', b'hello'),
        )
        assert client_for(mallory).get(reverse('message-file', kwargs={'pk': msg.pk})).status_code == 404
        r = client_for(alice).get(reverse('message-file', kwargs={'pk': msg.pk}))
        assert r.status_code == 200
        assert r['Content-Disposition'].startswith('attachment')


# ── Blocking & user privacy ──────────────────────────────────────────────────

class TestBlockingAndPrivacy:
    def test_blocked_user_disappears(self, alice, mallory):
        post = Post.objects.create(author=alice, content='hi')
        client_for(alice).post(reverse('user-block', kwargs={'pk': mallory.id}))
        c = client_for(mallory)
        assert c.get(reverse('user-detail', kwargs={'pk': alice.id})).status_code == 404
        assert c.get(reverse('post-detail', kwargs={'pk': post.pk})).status_code == 404

    def test_blocked_user_cannot_friend_request_or_message(self, alice, mallory):
        Block.objects.create(blocker=alice, blocked=mallory)
        c = client_for(mallory)
        assert c.post(reverse('friend-request-list'), {'receiver_id': alice.id}).status_code == 403
        assert c.post(reverse('chatroom-list'), {'member_ids': [alice.id]}, format='json').status_code == 403

    def test_block_removes_friendship(self, alice, bob):
        befriend(alice, bob)
        client_for(alice).post(reverse('user-block', kwargs={'pk': bob.id}))
        assert not FriendRequest.objects.filter(sender=alice, receiver=bob).exists()

    def test_unblock(self, alice, mallory):
        Block.objects.create(blocker=alice, blocked=mallory)
        r = client_for(alice).delete(reverse('user-block', kwargs={'pk': mallory.id}))
        assert r.data == {'blocked': False}
        assert not Block.objects.exists()

    def test_other_users_never_see_email_or_settings(self, alice, mallory):
        data = client_for(mallory).get(reverse('user-detail', kwargs={'pk': alice.id})).data
        for field in ('email', 'birth_date', 'privacy_messages', 'searchable'):
            assert field not in data

    def test_private_profile_trimmed(self, alice, mallory):
        alice.privacy_profile = 'private'
        alice.bio = 'secret bio'
        alice.save()
        data = client_for(mallory).get(reverse('user-detail', kwargs={'pk': alice.id})).data
        assert 'bio' not in data and data['username'] == 'alice'

    def test_unsearchable_users_hidden_from_search(self, alice, mallory):
        alice.searchable = False
        alice.save()
        r = client_for(mallory).get(reverse('user-list') + '?search=ali')
        assert r.data['results'] == []

    def test_no_user_directory(self, alice, mallory):
        assert client_for(mallory).get(reverse('user-list')).data['results'] == []

    def test_friend_request_privacy(self, alice, bob, mallory):
        alice.privacy_friend_requests = 'friends_of_friends'
        alice.save()
        assert client_for(mallory).post(reverse('friend-request-list'), {'receiver_id': alice.id}).status_code == 403
        befriend(alice, bob)
        befriend(bob, mallory)
        assert client_for(mallory).post(reverse('friend-request-list'), {'receiver_id': alice.id}).status_code == 201

    def test_friend_request_cannot_be_rewritten(self, alice, bob):
        fr = FriendRequest.objects.create(sender=alice, receiver=bob)
        r = client_for(alice).patch(reverse('friend-request-detail', kwargs={'pk': fr.pk}),
                                    {'status': 'accepted'}, format='json')
        assert r.status_code == 405

    def test_friends_list_privacy(self, alice, bob, mallory):
        befriend(alice, bob)
        alice.privacy_friends_list = 'friends'
        alice.save()
        assert client_for(mallory).get(reverse('user-friends', kwargs={'pk': alice.id})).status_code == 403
        assert client_for(bob).get(reverse('user-friends', kwargs={'pk': alice.id})).status_code == 200


# ── Account security ─────────────────────────────────────────────────────────

class TestAccountSecurity:
    def test_refresh_uses_cookie_and_rotates(self, alice):
        c = APIClient()
        login = c.post(reverse('login'), {'username': 'alice', 'password': PASSWORD})
        first = login.cookies['andromeda_refresh'].value
        r = c.post(reverse('token-refresh'))
        assert r.status_code == 200 and 'access' in r.data
        assert r.cookies['andromeda_refresh'].value != first
        # The rotated-out token is blacklisted.
        c.cookies['andromeda_refresh'] = first
        assert c.post(reverse('token-refresh')).status_code == 401

    def test_logout_revokes_refresh_cookie(self, alice):
        c = APIClient()
        c.post(reverse('login'), {'username': 'alice', 'password': PASSWORD})
        assert c.post(reverse('logout')).status_code == 204
        assert c.post(reverse('token-refresh')).status_code == 401

    def test_password_change_requires_current_password(self, alice):
        c = client_for(alice)
        r = c.post(reverse('password-change'), {'current_password': 'nope', 'new_password': 'a-brand-new-pass'})
        assert r.status_code == 400
        r = c.post(reverse('password-change'), {'current_password': PASSWORD, 'new_password': 'a-brand-new-pass'})
        assert r.status_code == 200
        alice.refresh_from_db()
        assert alice.check_password('a-brand-new-pass')

    def test_password_reset_does_not_reveal_accounts(self, alice):
        c = APIClient()
        known = c.post(reverse('password-reset'), {'email': 'alice@example.com'})
        unknown = c.post(reverse('password-reset'), {'email': 'nobody@example.com'})
        assert known.status_code == unknown.status_code == 202
        assert known.data == unknown.data

    def test_password_reset_flow(self, alice):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        uid = urlsafe_base64_encode(force_bytes(alice.pk))
        c = APIClient()
        bad = c.post(reverse('password-reset-confirm'), {'uid': uid, 'token': 'bad', 'new_password': 'reset-pass-123'})
        assert bad.status_code == 400
        token = default_token_generator.make_token(alice)
        ok = c.post(reverse('password-reset-confirm'), {'uid': uid, 'token': token, 'new_password': 'reset-pass-123'})
        assert ok.status_code == 200
        # Tokens are single-use: the password hash changed.
        again = c.post(reverse('password-reset-confirm'), {'uid': uid, 'token': token, 'new_password': 'other-pass-123'})
        assert again.status_code == 400

    def test_delete_account_requires_password(self, alice):
        c = client_for(alice)
        assert c.post(reverse('me-delete'), {'password': 'wrong'}).status_code == 400
        assert User.objects.filter(pk=alice.pk).exists()
        assert c.post(reverse('me-delete'), {'password': PASSWORD}).status_code == 204
        assert not User.objects.filter(pk=alice.pk).exists()

    def test_me_cannot_change_email_or_username(self, alice):
        client_for(alice).patch(reverse('me'), {'email': 'evil@x.com', 'username': 'root'}, format='json')
        alice.refresh_from_db()
        assert alice.email == 'alice@example.com' and alice.username == 'alice'

    def test_access_token_has_no_pii(self, alice):
        from rest_framework_simplejwt.tokens import AccessToken
        r = APIClient().post(reverse('login'), {'username': 'alice', 'password': PASSWORD})
        claims = AccessToken(r.data['access']).payload
        assert 'email' not in claims and 'username' not in claims

    def test_weak_password_rejected(self, db):
        r = APIClient().post(reverse('register'), {
            'username': 'weak', 'email': 'weak@example.com', 'first_name': 'W', 'last_name': 'P',
            'password': 'password1', 'password2': 'password1',
        })
        assert r.status_code == 400


class TestWebSocketTickets:
    def test_ticket_is_single_use(self, alice):
        r = client_for(alice).post(reverse('ws-ticket'))
        ticket = r.data['ticket']
        assert ws_tickets.redeem(ticket) == alice.id
        assert ws_tickets.redeem(ticket) is None

    def test_garbage_ticket(self):
        assert ws_tickets.redeem('x' * 500) is None
        assert ws_tickets.redeem('') is None


# ── Uploads ──────────────────────────────────────────────────────────────────

def _jpeg_with_exif():
    img = Image.new('RGB', (20, 20), 'red')
    exif = Image.Exif()
    exif[0x010F] = 'SpyCam'               # camera make
    exif[0x0132] = '2026:01:01 09:00:00'  # timestamp
    buf = io.BytesIO()
    img.save(buf, format='JPEG', exif=exif)
    return buf.getvalue()


class TestUploads:
    def test_exif_is_stripped(self, alice):
        upload = SimpleUploadedFile('me.jpg', _jpeg_with_exif(), content_type='image/jpeg')
        r = client_for(alice).post(reverse('post-list'), {'content': 'pic', 'image': upload}, format='multipart')
        assert r.status_code == 201, r.data
        post = Post.objects.get(pk=r.data['id'])
        with post.image.open('rb') as fh:
            assert not Image.open(fh).getexif()

    def test_stored_filename_is_random(self, alice):
        upload = SimpleUploadedFile('alice-passport.jpg', _jpeg_with_exif(), content_type='image/jpeg')
        r = client_for(alice).post(reverse('post-list'), {'image': upload}, format='multipart')
        assert 'passport' not in Post.objects.get(pk=r.data['id']).image.name

    def test_non_image_rejected(self, alice):
        upload = SimpleUploadedFile('evil.jpg', b'<?php system($_GET[1]); ?>', content_type='image/jpeg')
        r = client_for(alice).post(reverse('post-list'), {'image': upload}, format='multipart')
        assert r.status_code == 400

    def test_fake_video_rejected(self, alice):
        upload = SimpleUploadedFile('clip.mp4', b'MZ\x90\x00not a video', content_type='video/mp4')
        r = client_for(alice).post(reverse('video-list'), {'title': 't', 'video_file': upload}, format='multipart')
        assert r.status_code == 400

    def test_executable_attachment_rejected(self):
        from django.core.exceptions import ValidationError
        from core.validators import validate_attachment
        with pytest.raises(ValidationError):
            validate_attachment(SimpleUploadedFile('a.pdf', b'MZ\x90\x00'))
        with pytest.raises(ValidationError):
            validate_attachment(SimpleUploadedFile('page.html', b'<script>'))


def test_seed_command_builds_a_graph(db, settings):
    from django.core.management import call_command
    settings.DEBUG = True
    call_command('seed', users=15, stdout=io.StringIO())
    assert User.objects.filter(username__startswith='demo').count() == 15
    assert FriendRequest.objects.filter(status='accepted').exists()
    assert Post.objects.exists() and Listing.objects.exists()


def test_seed_refuses_in_production(db, settings):
    from django.core.management import call_command
    from django.core.management.base import CommandError
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command('seed', users=1)
