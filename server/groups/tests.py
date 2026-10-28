"""
Group roles, bans, rules, pins and invite links.

Personas: admin, moderator, member, stranger, banned, blocked (blocked by the
admin) and anonymous. Like ``core/test_security.py``, a failure here is a
security bug.
"""
import io
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from groups.models import Group, GroupBan, GroupInvite, GroupJoinRequest, GroupMember, GroupPinnedPost, GroupRule
from groups.views import GroupInviteThrottle
from notifications.models import Notification
from posts.models import Comment, Post
from users.models import Block

User = get_user_model()


def make_user(name):
    return User.objects.create_user(username=name, email=f'{name}@example.com', password='correct-horse-battery')


def client_for(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def url(name, group, **kw):
    return reverse(f'group-{name}', kwargs={'pk': group.pk, **kw})


@pytest.fixture
def people(db):
    names = ('admin', 'moderator', 'member', 'stranger', 'banned', 'blocked')
    return {n: make_user(n) for n in names}


def _group(people, privacy):
    group = Group.objects.create(name=f'{privacy} club', privacy=privacy, created_by=people['admin'])
    GroupMember.objects.create(group=group, user=people['admin'], role='admin')
    GroupMember.objects.create(group=group, user=people['moderator'], role='moderator')
    GroupMember.objects.create(group=group, user=people['member'], role='member')
    GroupBan.objects.create(group=group, user=people['banned'], banned_by=people['admin'])
    Block.objects.get_or_create(blocker=people['admin'], blocked=people['blocked'])
    return group


@pytest.fixture
def public_group(people):
    return _group(people, 'public')


@pytest.fixture
def private_group(people):
    return _group(people, 'private')


@pytest.fixture
def secret_group(people):
    return _group(people, 'secret')


# ── Anonymous ────────────────────────────────────────────────────────────────

class TestAnonymous:
    def test_everything_requires_auth(self, public_group):
        c = APIClient()
        for name in ('detail', 'members', 'rules', 'pinned', 'invites', 'bans'):
            assert c.get(url(name, public_group)).status_code == 401
        for name in ('join', 'ban', 'pin', 'remove-post'):
            assert c.post(url(name, public_group), {}).status_code == 401
        assert c.get(reverse('group-invite-redeem', kwargs={'token': 'x' * 43})).status_code == 401
        assert c.post(reverse('group-invite-redeem', kwargs={'token': 'x' * 43})).status_code == 401


# ── Bans and kicks ───────────────────────────────────────────────────────────

class TestBans:
    def test_banned_user_cannot_join_or_request(self, people, public_group, private_group):
        c = client_for(people['banned'])
        assert c.post(url('join', public_group)).status_code == 403
        assert c.post(url('join', private_group)).status_code == 403
        assert not GroupMember.objects.filter(user=people['banned']).exists()
        assert not GroupJoinRequest.objects.filter(user=people['banned']).exists()

    def test_banned_user_cannot_see_private_or_secret_content(self, people, private_group, secret_group):
        Post.objects.create(author=people['member'], content='inside', group=private_group)
        c = client_for(people['banned'])
        for name in ('members', 'pinned'):
            assert c.get(url(name, private_group)).status_code == 403
        assert c.get(url('detail', secret_group)).status_code == 404
        r = c.get(reverse('post-list') + f'?group={private_group.id}')
        assert r.data['results'] == []

    def test_only_admin_bans(self, people, public_group):
        target = people['member']
        for actor in ('moderator', 'member', 'stranger', 'banned'):
            r = client_for(people[actor]).post(url('ban', public_group), {'user_id': target.id})
            assert r.status_code == 403, actor
        assert public_group.memberships.filter(user=target).exists()
        r = client_for(people['admin']).post(url('ban', public_group), {'user_id': target.id, 'reason': 'spam'})
        assert r.status_code == 200
        assert not public_group.memberships.filter(user=target).exists()
        assert GroupBan.objects.get(group=public_group, user=target).reason == 'spam'
        public_group.refresh_from_db()
        assert public_group.members_count == 2

    def test_ban_hides_their_group_posts(self, people, public_group):
        post = Post.objects.create(author=people['member'], content='spam', group=public_group)
        outside = Post.objects.create(author=people['member'], content='elsewhere')
        client_for(people['admin']).post(url('ban', public_group), {'user_id': people['member'].id})
        ids = {p['id'] for p in client_for(people['stranger']).get(reverse('post-list')).data['results']}
        assert post.id not in ids and outside.id in ids

    def test_cannot_ban_self_or_another_admin(self, people, public_group):
        other_admin = make_user('admin2')
        GroupMember.objects.create(group=public_group, user=other_admin, role='admin')
        c = client_for(people['admin'])
        assert c.post(url('ban', public_group), {'user_id': people['admin'].id}).status_code == 400
        assert c.post(url('ban', public_group), {'user_id': other_admin.id}).status_code == 403

    def test_ban_rejects_bad_ids(self, people, public_group):
        c = client_for(people['admin'])
        assert c.post(url('ban', public_group), {'user_id': 'abc'}).status_code == 400
        assert c.post(url('ban', public_group), {'user_id': 999999}).status_code == 404

    def test_unban_and_ban_list_admin_only(self, people, public_group):
        for actor in ('moderator', 'member', 'stranger'):
            c = client_for(people[actor])
            assert c.get(url('bans', public_group)).status_code == 403
            assert c.post(url('unban', public_group), {'user_id': people['banned'].id}).status_code == 403
        c = client_for(people['admin'])
        assert [b['user']['id'] for b in c.get(url('bans', public_group)).data['results']] == [people['banned'].id]
        assert c.post(url('unban', public_group), {'user_id': people['banned'].id}).status_code == 200
        assert client_for(people['banned']).post(url('join', public_group)).status_code == 200

    def test_ban_list_hides_blocked_users(self, people, public_group):
        GroupBan.objects.create(group=public_group, user=people['blocked'])
        ids = {b['user']['id'] for b in client_for(people['admin']).get(url('bans', public_group)).data['results']}
        assert people['blocked'].id not in ids

    def test_approving_banned_users_request_is_refused(self, people, private_group):
        GroupJoinRequest.objects.create(group=private_group, user=people['banned'])
        jr = GroupJoinRequest.objects.get(user=people['banned'])
        r = client_for(people['admin']).post(url('decide-join-request', private_group, request_id=jr.id,
                                                 decision='approve'))
        assert r.status_code == 403
        assert not private_group.memberships.filter(user=people['banned']).exists()

    def test_admin_cannot_directly_add_banned_user(self, people, private_group):
        r = client_for(people['admin']).post(url('invite', private_group), {'user_id': people['banned'].id})
        assert r.status_code == 403

    def test_moderator_kicks_members_only(self, people, public_group):
        mod = client_for(people['moderator'])
        assert mod.post(url('remove-member', public_group), {'user_id': people['admin'].id}).status_code == 403
        assert mod.post(url('remove-member', public_group), {'user_id': people['member'].id}).status_code == 200
        # A kick is not a ban: they may come back.
        assert client_for(people['member']).post(url('join', public_group)).status_code == 200

    def test_member_cannot_kick(self, people, public_group):
        r = client_for(people['member']).post(url('remove-member', public_group), {'user_id': people['moderator'].id})
        assert r.status_code == 403


# ── Roles ────────────────────────────────────────────────────────────────────

class TestRoles:
    def test_only_admin_changes_roles(self, people, public_group):
        for actor in ('moderator', 'member', 'stranger'):
            r = client_for(people[actor]).post(url('set-role', public_group),
                                               {'user_id': people['member'].id, 'role': 'admin'})
            assert r.status_code == 403, actor
        assert _role(public_group, people['member']) == 'member'

    def test_last_admin_cannot_step_down(self, people, public_group):
        c = client_for(people['admin'])
        r = c.post(url('set-role', public_group), {'user_id': people['admin'].id, 'role': 'member'})
        assert r.status_code == 400
        assert c.post(url('leave', public_group)).status_code == 400
        c.post(url('set-role', public_group), {'user_id': people['moderator'].id, 'role': 'admin'})
        r = c.post(url('set-role', public_group), {'user_id': people['admin'].id, 'role': 'member'})
        assert r.status_code == 200
        assert _role(public_group, people['admin']) == 'member'

    def test_only_admin_edits_settings(self, people, public_group):
        detail = url('detail', public_group)
        for actor in ('moderator', 'member', 'stranger', 'banned'):
            r = client_for(people[actor]).patch(detail, {'name': 'Owned'}, format='json')
            assert r.status_code == 403, actor
        r = client_for(people['admin']).patch(detail, {'name': 'Renamed', 'privacy': 'private'}, format='json')
        assert r.status_code == 200
        public_group.refresh_from_db()
        assert (public_group.name, public_group.privacy) == ('Renamed', 'private')

    def test_settings_cannot_touch_counters_or_creator(self, people, public_group):
        client_for(people['admin']).patch(url('detail', public_group),
                                          {'members_count': 9999, 'created_by': people['stranger'].id}, format='json')
        public_group.refresh_from_db()
        assert public_group.members_count != 9999 and public_group.created_by_id == people['admin'].id

    def test_cover_is_sanitised(self, people, public_group):
        img = Image.new('RGB', (10, 10), 'blue')
        exif = Image.Exif()
        exif[0x010F] = 'SpyCam'
        buf = io.BytesIO()
        img.save(buf, format='JPEG', exif=exif)
        upload = SimpleUploadedFile('home-address.jpg', buf.getvalue(), content_type='image/jpeg')
        r = client_for(people['admin']).patch(url('detail', public_group), {'cover_photo': upload}, format='multipart')
        assert r.status_code == 200, r.data
        public_group.refresh_from_db()
        assert 'home-address' not in public_group.cover_photo.name
        with public_group.cover_photo.open('rb') as fh:
            assert not Image.open(fh).getexif()

    def test_non_image_cover_rejected(self, people, public_group):
        upload = SimpleUploadedFile('x.jpg', b'<?php echo 1; ?>', content_type='image/jpeg')
        r = client_for(people['admin']).patch(url('detail', public_group), {'cover_photo': upload}, format='multipart')
        assert r.status_code == 400


def _role(group, user):
    return GroupMember.objects.get(group=group, user=user).role


# ── Moderation of content ────────────────────────────────────────────────────

class TestContentModeration:
    def test_moderator_removes_member_post_and_comment(self, people, public_group):
        post = Post.objects.create(author=people['member'], content='rude', group=public_group)
        comment = Comment.objects.create(author=people['member'], post=post, content='ruder')
        mod = client_for(people['moderator'])
        assert mod.post(url('remove-comment', public_group), {'comment_id': comment.id}).status_code == 200
        assert mod.post(url('remove-post', public_group), {'post_id': post.id}).status_code == 200
        assert not Post.objects.filter(pk=post.pk).exists()

    def test_member_and_stranger_cannot_remove(self, people, public_group):
        post = Post.objects.create(author=people['moderator'], content='x', group=public_group)
        for actor in ('member', 'stranger', 'banned'):
            assert client_for(people[actor]).post(url('remove-post', public_group),
                                                  {'post_id': post.id}).status_code == 403
        assert Post.objects.filter(pk=post.pk).exists()

    def test_moderator_cannot_remove_admin_post(self, people, public_group):
        post = Post.objects.create(author=people['admin'], content='x', group=public_group)
        r = client_for(people['moderator']).post(url('remove-post', public_group), {'post_id': post.id})
        assert r.status_code == 403

    def test_cannot_remove_posts_outside_the_group(self, people, public_group):
        other = Group.objects.create(name='Other', created_by=people['stranger'])
        elsewhere = Post.objects.create(author=people['stranger'], content='x', group=other)
        personal = Post.objects.create(author=people['stranger'], content='y')
        c = client_for(people['admin'])
        for post in (elsewhere, personal):
            assert c.post(url('remove-post', public_group), {'post_id': post.id}).status_code == 404
        assert Post.objects.filter(pk__in=[elsewhere.pk, personal.pk]).count() == 2


# ── Pins ─────────────────────────────────────────────────────────────────────

class TestPins:
    def test_moderator_pins_and_feed_shows_them(self, people, public_group):
        post = Post.objects.create(author=people['member'], content='welcome', group=public_group)
        assert client_for(people['moderator']).post(url('pin', public_group), {'post_id': post.id}).status_code == 200
        r = client_for(people['stranger']).get(url('pinned', public_group))
        assert [p['id'] for p in r.data] == [post.id]

    def test_member_cannot_pin(self, people, public_group):
        post = Post.objects.create(author=people['member'], content='me me me', group=public_group)
        for actor in ('member', 'stranger'):
            assert client_for(people[actor]).post(url('pin', public_group), {'post_id': post.id}).status_code == 403
            assert client_for(people[actor]).post(url('unpin', public_group), {'post_id': post.id}).status_code == 403
        assert not GroupPinnedPost.objects.exists()

    def test_cannot_pin_foreign_post(self, people, public_group):
        post = Post.objects.create(author=people['stranger'], content='ad')
        r = client_for(people['admin']).post(url('pin', public_group), {'post_id': post.id})
        assert r.status_code == 404

    def test_pin_limit(self, people, public_group):
        c = client_for(people['admin'])
        posts = [Post.objects.create(author=people['admin'], content=str(i), group=public_group) for i in range(4)]
        for p in posts[:3]:
            assert c.post(url('pin', public_group), {'post_id': p.id}).status_code == 200
        assert c.post(url('pin', public_group), {'post_id': posts[3].id}).status_code == 400
        assert c.post(url('unpin', public_group), {'post_id': posts[0].id}).status_code == 200
        assert c.post(url('pin', public_group), {'post_id': posts[3].id}).status_code == 200

    def test_pinned_respects_privacy_bans_and_blocks(self, people, private_group):
        by_member = Post.objects.create(author=people['member'], content='m', group=private_group)
        by_admin = Post.objects.create(author=people['admin'], content='a', group=private_group)
        for p in (by_member, by_admin):
            GroupPinnedPost.objects.create(group=private_group, post=p)
        assert client_for(people['stranger']).get(url('pinned', private_group)).status_code == 403
        # The blocked user (once a member) doesn't see the admin's pinned post.
        GroupMember.objects.create(group=private_group, user=people['blocked'])
        ids = [p['id'] for p in client_for(people['blocked']).get(url('pinned', private_group)).data]
        assert ids == [by_member.id]
        # Banning the author hides their pinned post.
        client_for(people['admin']).post(url('ban', private_group), {'user_id': people['member'].id})
        ids = [p['id'] for p in client_for(people['moderator']).get(url('pinned', private_group)).data]
        assert ids == [by_admin.id]


# ── Rules ────────────────────────────────────────────────────────────────────

class TestRules:
    RULES = {'rules': [{'title': 'Be kind', 'description': 'No insults.'}, {'title': 'No spam'}]}

    def test_admin_sets_ordered_rules_others_read(self, people, private_group):
        r = client_for(people['admin']).post(url('rules', private_group), self.RULES, format='json')
        assert r.status_code == 200
        assert [rule['title'] for rule in r.data] == ['Be kind', 'No spam']
        # Shown at join time, so non-members of a private group can read them.
        r = client_for(people['stranger']).get(url('rules', private_group))
        assert [rule['position'] for rule in r.data] == [0, 1]

    def test_non_admins_cannot_set_rules(self, people, public_group):
        for actor in ('moderator', 'member', 'stranger', 'banned'):
            r = client_for(people[actor]).post(url('rules', public_group), self.RULES, format='json')
            assert r.status_code == 403, actor
        assert not GroupRule.objects.exists()

    def test_secret_group_rules_hidden(self, people, secret_group):
        assert client_for(people['stranger']).get(url('rules', secret_group)).status_code == 404

    def test_rule_limits(self, people, public_group):
        c = client_for(people['admin'])
        too_many = {'rules': [{'title': f'r{i}'} for i in range(21)]}
        assert c.post(url('rules', public_group), too_many, format='json').status_code == 400
        too_long = {'rules': [{'title': 'x' * 121}]}
        assert c.post(url('rules', public_group), too_long, format='json').status_code == 400


# ── Invite links ─────────────────────────────────────────────────────────────

def _create_invite(user, group, **data):
    return client_for(user).post(url('invites', group), data, format='json')


def _redeem_url(token):
    return reverse('group-invite-redeem', kwargs={'token': token})


class TestInvites:
    def test_admin_and_moderator_create_others_cannot(self, people, secret_group, private_group):
        assert _create_invite(people['admin'], secret_group).status_code == 201
        assert _create_invite(people['moderator'], secret_group).status_code == 201
        assert _create_invite(people['member'], secret_group).status_code == 403
        assert _create_invite(people['stranger'], private_group).status_code == 403
        assert _create_invite(people['stranger'], secret_group).status_code == 404
        for actor in ('member', 'stranger'):
            assert client_for(people[actor]).get(url('invites', private_group)).status_code == 403

    def test_token_stored_hashed_and_shown_once(self, people, secret_group):
        r = _create_invite(people['admin'], secret_group)
        token = r.data['token']
        assert len(token) >= 40
        invite = GroupInvite.objects.get()
        assert invite.token_hash != token and token not in invite.token_hash
        assert invite.token_hash == GroupInvite.hash_token(token)
        listed = client_for(people['admin']).get(url('invites', secret_group)).data
        assert 'token' not in listed[0] and 'token_hash' not in listed[0]

    def test_secret_group_join_via_link(self, people, secret_group):
        token = _create_invite(people['admin'], secret_group).data['token']
        c = client_for(people['stranger'])
        # Never discoverable through lists or search, even with a link in hand.
        assert secret_group.id not in {g['id'] for g in c.get(reverse('group-list')).data['results']}
        preview = c.get(_redeem_url(token))
        assert preview.status_code == 200
        assert preview.data['group']['name'] == secret_group.name and preview.data['is_member'] is False
        assert 'members' not in preview.data['group']
        r = c.post(_redeem_url(token))
        assert r.data == {'status': 'joined', 'group_id': secret_group.id}
        assert secret_group.memberships.filter(user=people['stranger']).exists()
        assert c.get(url('detail', secret_group)).status_code == 200
        assert GroupInvite.objects.get().uses_count == 1

    def test_private_group_join_via_link_skips_approval(self, people, private_group):
        GroupJoinRequest.objects.create(group=private_group, user=people['stranger'])
        token = _create_invite(people['moderator'], private_group).data['token']
        assert client_for(people['stranger']).post(_redeem_url(token)).status_code == 200
        assert private_group.memberships.filter(user=people['stranger']).exists()
        assert not GroupJoinRequest.objects.filter(user=people['stranger']).exists()

    def test_banned_cannot_use_link(self, people, secret_group):
        token = _create_invite(people['admin'], secret_group).data['token']
        c = client_for(people['banned'])
        assert c.get(_redeem_url(token)).status_code == 403
        assert c.post(_redeem_url(token)).status_code == 403
        assert not secret_group.memberships.filter(user=people['banned']).exists()

    def test_blocked_by_creator_cannot_use_link(self, people, secret_group):
        token = _create_invite(people['admin'], secret_group).data['token']
        assert client_for(people['blocked']).post(_redeem_url(token)).status_code == 404
        assert not secret_group.memberships.filter(user=people['blocked']).exists()

    def test_expired_revoked_and_used_up_links_fail(self, people, secret_group):
        expired = _create_invite(people['admin'], secret_group, expires_in_hours=1).data
        GroupInvite.objects.filter(pk=expired['id']).update(expires_at=timezone.now() - timedelta(seconds=1))
        revoked = _create_invite(people['admin'], secret_group).data
        r = client_for(people['moderator']).post(url('revoke-invite', secret_group, invite_id=revoked['id']))
        assert r.status_code == 200
        single = _create_invite(people['admin'], secret_group, max_uses=1).data
        assert client_for(people['member']).post(_redeem_url(single['token'])).data['status'] == 'already_member'
        assert client_for(make_user('first')).post(_redeem_url(single['token'])).status_code == 200
        c = client_for(people['stranger'])
        for invite in (expired, revoked, single):
            assert c.get(_redeem_url(invite['token'])).status_code == 404
            assert c.post(_redeem_url(invite['token'])).status_code == 404
        assert not secret_group.memberships.filter(user=people['stranger']).exists()

    def test_garbage_and_guessed_tokens(self, people, secret_group):
        _create_invite(people['admin'], secret_group)
        c = client_for(people['stranger'])
        hashed = GroupInvite.objects.get().token_hash  # the stored digest is not a working token
        for token in ('short', 'a' * 43, hashed, 'x' * 200, '..%2F..'):
            assert c.post(_redeem_url(token)).status_code == 404

    def test_only_group_staff_revoke(self, people, private_group):
        invite = _create_invite(people['admin'], private_group).data
        for actor in ('member', 'stranger'):
            r = client_for(people[actor]).post(url('revoke-invite', private_group, invite_id=invite['id']))
            assert r.status_code == 403
        assert GroupInvite.objects.get().revoked_at is None

    def test_cannot_revoke_another_groups_invite(self, people, private_group, db):
        other = Group.objects.create(name='Other', privacy='private', created_by=people['stranger'])
        GroupMember.objects.create(group=other, user=people['stranger'], role='admin')
        invite = _create_invite(people['stranger'], other).data
        r = client_for(people['admin']).post(url('revoke-invite', private_group, invite_id=invite['id']))
        assert r.status_code == 404

    def test_invite_limits_validated(self, people, private_group):
        assert _create_invite(people['admin'], private_group, expires_in_hours=24 * 31).status_code == 400
        assert _create_invite(people['admin'], private_group, max_uses=0).status_code == 400

    def test_redemption_is_rate_limited(self, people, secret_group, monkeypatch):
        cache.clear()
        monkeypatch.setattr(GroupInviteThrottle, 'rate', '3/min', raising=False)
        c = client_for(people['stranger'])
        codes = [c.post(_redeem_url('z' * 43)).status_code for _ in range(4)]
        assert codes == [404, 404, 404, 429]
        cache.clear()


# ── Discovery, notifications ─────────────────────────────────────────────────

class TestDiscoveryAndNotifications:
    def test_secret_group_not_in_search(self, people, secret_group):
        r = client_for(people['stranger']).get(reverse('search') + '?q=secret')
        assert r.data['results']['groups'] == []

    def test_approval_notifies_requester(self, people, private_group):
        client_for(people['stranger']).post(url('join', private_group))
        jr = GroupJoinRequest.objects.get(user=people['stranger'])
        client_for(people['moderator']).post(url('decide-join-request', private_group, request_id=jr.id,
                                                 decision='approve'))
        n = Notification.objects.get(recipient=people['stranger'])
        assert n.extra == {'kind': 'group_join_approved', 'group_id': private_group.id}

    def test_serializer_flags(self, people, public_group, private_group):
        client_for(people['stranger']).post(url('join', private_group))
        assert client_for(people['stranger']).get(url('detail', private_group)).data['has_requested'] is True
        assert client_for(people['banned']).get(url('detail', public_group)).data['is_banned'] is True
        assert client_for(people['member']).get(url('detail', public_group)).data['is_banned'] is False
