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

    def test_stranger_cannot_change_listing_status_or_add_images(self, alice, mallory):
        listing = Listing.objects.create(seller=alice, title='Couch', price=100)
        c = client_for(mallory)
        assert c.patch(reverse('listing-detail', kwargs={'pk': listing.pk}), {'status': 'reserved'},
                       format='json').status_code == 403
        r = c.post(reverse('listing-upload-images', kwargs={'pk': listing.pk}),
                   {'images': SimpleUploadedFile('a.jpg', _jpeg_with_exif(), content_type='image/jpeg')},
                   format='multipart')
        assert r.status_code == 403
        listing.refresh_from_db()
        assert listing.status == 'active' and not listing.images.exists()

    def test_sold_listing_and_precise_location_stay_private(self, alice, mallory):
        sold = Listing.objects.create(seller=alice, title='Bike', price=100, status='sold')
        mine = Listing.objects.create(seller=alice, title='Desk', price=10, latitude=-33.92, longitude=18.42)
        c = client_for(mallory)
        assert c.get(reverse('listing-detail', kwargs={'pk': sold.pk})).status_code == 404
        data = c.get(reverse('listing-detail', kwargs={'pk': mine.pk})).data
        assert 'latitude' not in data and data['approx_point'] == {'latitude': -33.9, 'longitude': 18.4}

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

    def test_invisible_post_actions_404(self, alice, bob, mallory):
        """Revisions, save and hide behave like the post doesn't exist for strangers and blocked users."""
        befriend(alice, bob)
        post = Post.objects.create(author=alice, content='f', privacy='friends')
        Block.objects.create(blocker=alice, blocked=bob)
        for user in (mallory, bob):
            c = client_for(user)
            for name in ('post-revisions', 'post-bookmark', 'post-hide'):
                method = c.get if name == 'post-revisions' else c.post
                assert method(reverse(name, kwargs={'pk': post.pk})).status_code == 404
        anon = APIClient()
        assert anon.get(reverse('post-revisions', kwargs={'pk': post.pk})).status_code == 401
        assert anon.get(reverse('post-saved')).status_code == 401

    def test_comment_edit_and_delete_rules(self, alice, bob, mallory):
        from posts.models import Comment
        post = Post.objects.create(author=alice, content='public')
        comment = Comment.objects.create(post=post, author=bob, content='mine')
        c = client_for(mallory)
        url = reverse('comment-detail', kwargs={'pk': comment.pk})
        assert c.patch(url, {'content': 'pwned'}, format='json').status_code == 403
        assert c.delete(url).status_code == 403
        # The post's author may delete it but never rewrite it.
        assert client_for(alice).patch(url, {'content': 'x'}, format='json').status_code == 403
        comment.refresh_from_db()
        assert comment.content == 'mine'
        assert client_for(alice).delete(url).status_code == 204

    def test_comments_on_invisible_posts_unreachable(self, alice, mallory):
        from posts.models import Comment
        post = Post.objects.create(author=alice, content='p', privacy='private')
        comment = Comment.objects.create(post=post, author=alice, content='c')
        c = client_for(mallory)
        assert c.get(reverse('comment-detail', kwargs={'pk': comment.pk})).status_code == 404
        assert c.post(reverse('comment-like', kwargs={'pk': comment.pk})).status_code == 404
        assert c.delete(reverse('comment-detail', kwargs={'pk': comment.pk})).status_code == 404

    def test_feed_hides_strangers_and_blocked(self, alice, bob, mallory):
        befriend(alice, bob)
        Post.objects.create(author=mallory, content='stranger')
        friend_post = Post.objects.create(author=bob, content='friend', privacy='friends')
        for sort in ('top', 'latest'):
            r = client_for(alice).get(reverse('post-list') + f'?feed=true&sort={sort}')
            assert [p['id'] for p in r.data['results']] == [friend_post.id]
        Block.objects.create(blocker=bob, blocked=alice)
        r = client_for(alice).get(reverse('post-list') + '?feed=true')
        assert r.data['results'] == []


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

    def test_banned_user_cannot_rejoin(self, alice, mallory):
        group = Group.objects.create(name='Runners', created_by=alice)
        GroupMember.objects.create(group=group, user=alice, role='admin')
        GroupMember.objects.create(group=group, user=mallory, role='member')
        client_for(alice).post(reverse('group-ban', kwargs={'pk': group.pk}), {'user_id': mallory.id})
        assert client_for(mallory).post(reverse('group-join', kwargs={'pk': group.pk})).status_code == 403
        assert not group.memberships.filter(user=mallory).exists()

    def test_moderator_cannot_ban_or_edit(self, alice, bob, mallory):
        group = Group.objects.create(name='Runners', created_by=alice)
        GroupMember.objects.create(group=group, user=alice, role='admin')
        GroupMember.objects.create(group=group, user=bob, role='moderator')
        c = client_for(bob)
        assert c.post(reverse('group-ban', kwargs={'pk': group.pk}), {'user_id': mallory.id}).status_code == 403
        assert c.patch(reverse('group-detail', kwargs={'pk': group.pk}), {'name': 'x'}, format='json').status_code == 403

    def test_invite_token_is_hashed_and_single_purpose(self, alice, mallory):
        from groups.models import GroupInvite
        group = Group.objects.create(name='Hidden', privacy='secret', created_by=alice)
        GroupMember.objects.create(group=group, user=alice, role='admin')
        token = client_for(alice).post(reverse('group-invites', kwargs={'pk': group.pk})).data['token']
        assert not GroupInvite.objects.filter(token_hash=token).exists()
        c = client_for(mallory)
        assert group.id not in {g['id'] for g in c.get(reverse('group-list')).data['results']}
        assert c.post(reverse('group-invite-redeem', kwargs={'token': token})).status_code == 200
        assert group.memberships.filter(user=mallory).exists()


class TestPages:
    def test_only_staff_can_verify_page(self, alice, mallory):
        page = Page.objects.create(name='Shop', username='shop', created_by=alice)
        c = client_for(alice)
        assert c.patch(reverse('page-detail', kwargs={'pk': page.pk}), {'is_verified': True}, format='json').status_code == 200
        assert c.post(reverse('page-verify', kwargs={'pk': page.pk})).status_code == 403
        page.refresh_from_db()
        assert page.is_verified is False

    def test_stranger_cannot_manage_page_roles(self, alice, mallory):
        page = Page.objects.create(name='Shop', username='shop', created_by=alice)
        r = client_for(mallory).post(reverse('page-admins', kwargs={'pk': page.pk}),
                                     {'user_id': mallory.id, 'role': 'admin'})
        assert r.status_code == 403
        assert client_for(mallory).get(reverse('page-admins', kwargs={'pk': page.pk})).status_code == 403


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

    @pytest.fixture
    def crew(self, alice, bob):
        room = ChatRoom.objects.create(room_type='group', name='Crew', created_by=alice)
        ChatMember.objects.create(room=room, user=alice, role='admin')
        ChatMember.objects.create(room=room, user=bob)
        return room

    def test_non_member_cannot_search_or_see_presence(self, crew, alice, mallory):
        Message.objects.create(room=crew, sender=alice, content='secret plans')
        c = client_for(mallory)
        assert c.get(reverse('chatroom-search', kwargs={'pk': crew.pk}) + '?q=secret').status_code == 404
        assert c.get(reverse('chatroom-presence', kwargs={'pk': crew.pk})).status_code == 404
        assert c.get(reverse('chatroom-messages', kwargs={'pk': crew.pk}) + '?after_id=0').status_code == 404
        assert c.get(reverse('chatroom-unread')).data['total'] == 0

    def test_removed_member_loses_room_and_attachments(self, crew, alice, bob):
        msg = Message.objects.create(room=crew, sender=alice, message_type='file',
                                     file=SimpleUploadedFile('notes.txt', b'hello'))
        assert client_for(alice).post(reverse('chatroom-remove-member', kwargs={'pk': crew.pk}),
                                      {'user_id': bob.id}).status_code == 200
        c = client_for(bob)
        assert c.get(reverse('message-file', kwargs={'pk': msg.pk})).status_code == 404
        assert c.get(reverse('chatroom-search', kwargs={'pk': crew.pk}) + '?q=hello').status_code == 404
        assert c.post(reverse('message-list'), {'room': crew.id, 'content': 'hi'}).status_code == 403

    def test_only_admins_manage_group(self, crew, bob, mallory):
        for user, expected in ((bob, 403), (mallory, 404)):
            c = client_for(user)
            assert c.patch(reverse('chatroom-rename', kwargs={'pk': crew.pk}), {'name': 'x'},
                           format='json').status_code == expected
            assert c.post(reverse('chatroom-set-role', kwargs={'pk': crew.pk}),
                          {'user_id': user.id, 'role': 'admin'}).status_code == expected
            assert c.post(reverse('chatroom-add-member', kwargs={'pk': crew.pk}),
                          {'user_id': user.id}).status_code == expected
            assert c.delete(reverse('chatroom-avatar', kwargs={'pk': crew.pk})).status_code == expected
        assert client_for(bob).post(reverse('chatroom-remove-member', kwargs={'pk': crew.pk}),
                                    {'user_id': crew.created_by_id}).status_code == 403
        assert ChatMember.objects.filter(room=crew).count() == 2
        assert ChatMember.objects.get(room=crew, user=bob).role == 'member'

    def test_blocked_user_cannot_be_added_to_group(self, crew, alice, mallory):
        Block.objects.create(blocker=mallory, blocked=alice)
        r = client_for(alice).post(reverse('chatroom-add-member', kwargs={'pk': crew.pk}), {'user_id': mallory.id})
        assert r.status_code == 403
        assert not ChatMember.objects.filter(room=crew, user=mallory).exists()

    def test_non_member_cannot_react_edit_or_delete(self, crew, alice, mallory):
        from chats import services
        msg = Message.objects.create(room=crew, sender=alice, content='x')
        for action, args in ((services.set_reaction, ('like',)), (services.edit_message, ('pwned',)),
                             (services.delete_message, ())):
            with pytest.raises(services.ChatActionError):
                action(mallory, crew.id, msg.id, *args)
        msg.refresh_from_db()
        assert msg.content == 'x' and not msg.is_deleted and not msg.reactions.exists()

    def test_voice_note_must_be_audio(self, crew, alice):
        disguised = SimpleUploadedFile('note.webm', b'<html><script>alert(1)</script>', content_type='audio/webm')
        r = client_for(alice).post(reverse('message-list'), {'room': crew.id, 'message_type': 'voice',
                                                             'file': disguised}, format='multipart')
        assert r.status_code == 400
        assert not crew.messages.exists()


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
        assert c.post(reverse('me-delete'), {'password': PASSWORD}).status_code == 202
        alice.refresh_from_db()
        assert alice.deletion_scheduled_at is not None  # erased when the grace period ends

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
            'password': 'password1', 'password2': 'password1', 'accept_terms': True,
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


# ── Watch ────────────────────────────────────────────────────────────────────

def _processed_video(owner, is_public=True, **extra):
    """A ready video with real files in storage, as the pipeline leaves it."""
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage
    from watch.access import asset_key

    video = Video.objects.create(uploader=owner, title='clip', video_file='private/watch/originals/x.mp4',
                                 status='ready', is_public=is_public, asset_root='public' if is_public else 'private',
                                 asset_id=f'{owner.id:04d}{Video.objects.count():028d}', duration=60,
                                 asset_files=['master.m3u8', 'thumb.jpg', '360p/index.m3u8', '360p/seg_00000.ts'],
                                 captions_vtt='WEBVTT\n\n', transcript='secret words', **extra)
    for rel in video.asset_files:
        default_storage.save(asset_key(video, rel), ContentFile(b'#EXTM3U\n'))
    return video


def _stream_url(video, user, path='master.m3u8'):
    from watch.access import stream_token
    return reverse('watch-stream', kwargs={'token': stream_token(video.pk, user.pk), 'path': path})


class TestWatch:
    """Private videos: owner only. Blocks: both ways. Anonymous: nothing."""

    READ_ROUTES = ['video-detail', 'video-captions', 'video-transcript', 'video-progress', 'video-comments']

    def test_private_video_is_owner_only(self, alice, mallory):
        video = _processed_video(alice, is_public=False)
        for name in self.READ_ROUTES:
            url = reverse(name, kwargs={'pk': video.pk})
            assert client_for(alice).get(url).status_code == 200, name
            assert client_for(mallory).get(url).status_code == 404, name
            assert APIClient().get(url).status_code == 401, name
        c = client_for(mallory)
        assert c.post(reverse('video-like', kwargs={'pk': video.pk})).status_code == 404
        assert c.post(reverse('video-progress', kwargs={'pk': video.pk}), {'position_s': 1},
                      format='json').status_code == 404
        assert c.post(reverse('video-comments', kwargs={'pk': video.pk}), {'content': 'hi'},
                      format='json').status_code == 404
        assert video.pk not in [v['id'] for v in c.get(reverse('video-list')).data['results']]

    def test_processing_and_failed_videos_are_owner_only(self, alice, mallory):
        for state in ('processing', 'failed'):
            video = Video.objects.create(uploader=alice, title=state, video_file='private/x.mp4', status=state,
                                         failure_reason='Videos can be at most 20 minutes long.')
            assert client_for(mallory).get(reverse('video-detail', kwargs={'pk': video.pk})).status_code == 404
            assert client_for(mallory).post(reverse('video-retry', kwargs={'pk': video.pk})).status_code == 404

    def test_stranger_cannot_retry_public_video(self, alice, mallory):
        video = _processed_video(alice)
        assert client_for(mallory).post(reverse('video-retry', kwargs={'pk': video.pk})).status_code == 403

    def test_original_upload_is_never_exposed(self, alice, bob):
        video = _processed_video(alice)
        body = client_for(bob).get(reverse('video-detail', kwargs={'pk': video.pk})).data
        assert 'video_file' not in body and 'originals' not in str(body)
        assert body['failure_reason'] == ''

    def test_blocked_users_cannot_see_videos_or_channels(self, alice, mallory):
        video = _processed_video(alice)
        url = _stream_url(video, mallory)  # issued before the block
        Block.objects.create(blocker=alice, blocked=mallory)
        c = client_for(mallory)
        for name in self.READ_ROUTES:
            assert c.get(reverse(name, kwargs={'pk': video.pk})).status_code == 404, name
        assert c.get(url).status_code == 404
        assert c.get(reverse('channel-detail', kwargs={'pk': alice.pk})).status_code == 404
        assert c.post(reverse('channel-subscribe', kwargs={'pk': alice.pk})).status_code == 404
        assert c.get(reverse('video-list'), {'uploader': alice.pk}).data['results'] == []
        # And the other way round.
        mine = _processed_video(mallory)
        assert client_for(alice).get(reverse('video-detail', kwargs={'pk': mine.pk})).status_code == 404

    def test_history_hides_videos_that_became_invisible(self, alice, bob):
        from watch.models import WatchProgress
        video = _processed_video(alice)
        WatchProgress.objects.create(user=bob, video=video, position_s=10)
        assert len(client_for(bob).get(reverse('watch-history-list')).data['results']) == 1
        Video.objects.filter(pk=video.pk).update(is_public=False)
        assert client_for(bob).get(reverse('watch-history-list')).data['results'] == []

    def test_history_is_per_user(self, alice, bob, mallory):
        from watch.models import WatchProgress
        video = _processed_video(alice)
        WatchProgress.objects.create(user=bob, video=video, position_s=10)
        c = client_for(mallory)
        assert c.get(reverse('watch-history-list')).data['results'] == []
        c.delete(reverse('watch-history-detail', kwargs={'video_id': video.pk}))
        c.delete(reverse('watch-history-clear'))
        assert WatchProgress.objects.filter(user=bob).exists()

    def test_anonymous_gets_nothing(self, alice):
        anon = APIClient()
        for url in (reverse('video-list'), reverse('watch-history-list'), reverse('channel-list'),
                    reverse('channel-detail', kwargs={'pk': alice.pk})):
            assert anon.get(url).status_code == 401, url
        assert anon.post(reverse('channel-subscribe', kwargs={'pk': alice.pk})).status_code == 401

    def test_stream_link_is_bound_to_viewer_and_video(self, alice, bob, mallory):
        private = _processed_video(alice, is_public=False)
        anon = APIClient()
        r = anon.get(_stream_url(private, alice))  # the link is the credential, re-checked for alice
        assert r.status_code == 200 and r['Cache-Control'] == 'private, no-store'
        assert r['Content-Security-Policy'] == "default-src 'none'; sandbox"
        assert anon.get(_stream_url(private, mallory)).status_code == 404
        # Revoked as soon as the video stops being visible to the link's owner.
        public = _processed_video(alice)
        url = _stream_url(public, bob)
        assert anon.get(url).status_code == 200
        Video.objects.filter(pk=public.pk).update(is_public=False)
        assert anon.get(url).status_code == 404

    def test_stream_link_tampering(self, alice, settings):
        from watch.access import stream_token
        video = _processed_video(alice, is_public=False)
        token = stream_token(video.pk, alice.pk)
        anon = APIClient()
        assert anon.get(f'/api/watch/stream/{token[:-3]}abc/master.m3u8').status_code == 404
        other = _processed_video(alice, is_public=False)
        swapped = stream_token(other.pk, alice.pk).split(':')[0] + ':' + token.split(':', 1)[1]
        assert anon.get(f'/api/watch/stream/{swapped}/master.m3u8').status_code == 404
        for path in ('../../../etc/passwd', '..%2F..%2Fsecret', '360p/../../x', 'source', 'audio.webm',
                     '1080p/index.m3u8'):
            assert anon.get(f'/api/watch/stream/{token}/{path}').status_code == 404, path
        assert anon.post(f'/api/watch/stream/{token}/master.m3u8').status_code == 405
        settings.WATCH_STREAM_TOKEN_MAX_AGE = -1
        assert anon.get(f'/api/watch/stream/{token}/master.m3u8').status_code == 404

    def test_stream_link_for_deactivated_user(self, alice):
        video = _processed_video(alice, is_public=False)
        url = _stream_url(video, alice)
        User.objects.filter(pk=alice.pk).update(is_active=False)
        assert APIClient().get(url).status_code == 404

    def test_cannot_edit_others_video_visibility(self, alice, mallory):
        video = _processed_video(alice, is_public=False)
        url = reverse('video-detail', kwargs={'pk': video.pk})
        assert client_for(mallory).patch(url, {'is_public': True}, format='json').status_code == 404
        public = _processed_video(alice)
        r = client_for(mallory).patch(reverse('video-detail', kwargs={'pk': public.pk}), {'is_public': False},
                                      format='json')
        assert r.status_code == 403


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


class TestSearch:
    def test_search_respects_privacy(self, alice, mallory):
        Post.objects.create(author=alice, content='galaxy secrets', privacy='private')
        public = Post.objects.create(author=alice, content='galaxy photos', privacy='public')
        Group.objects.create(name='galaxy hidden', privacy='secret', created_by=alice)
        r = client_for(mallory).get(reverse('search') + '?q=galaxy')
        assert r.status_code == 200
        assert [p['id'] for p in r.data['results']['posts']] == [public.id]
        assert r.data['results']['groups'] == []

    def test_search_hides_blocked_and_unsearchable(self, alice, bob, mallory):
        Block.objects.create(blocker=alice, blocked=mallory)
        bob.searchable = False
        bob.save()
        r = client_for(mallory).get(reverse('search') + '?q=a&type=people')
        assert r.status_code == 400  # too short
        names = {u['username'] for u in client_for(mallory).get(
            reverse('search') + '?q=o&type=people'.replace('q=o', 'q=bo')).data['results']['people']}
        assert 'bob' not in names
        names = {u['username'] for u in client_for(mallory).get(
            reverse('search') + '?q=al&type=people').data['results']['people']}
        assert 'alice' not in names
