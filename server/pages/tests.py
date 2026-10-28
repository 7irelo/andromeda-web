"""
Page editing, roles, verification and followers.

Personas: creator (admin), co-admin, editor, analyst, follower, stranger,
blocked (blocked by the creator), staff and anonymous.
"""
import io

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from rest_framework.test import APIClient

from notifications.models import Notification
from pages.models import Page, PageAdmin, PageFollow
from posts.models import Post
from users.models import Block

User = get_user_model()


def make_user(name, **extra):
    return User.objects.create_user(username=name, email=f'{name}@example.com', password='correct-horse-battery',
                                    **extra)


def client_for(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def url(name, page, **kw):
    return reverse(f'page-{name}', kwargs={'pk': page.pk, **kw})


@pytest.fixture
def people(db):
    names = ('creator', 'coadmin', 'editor', 'analyst', 'follower', 'stranger', 'blocked')
    users = {n: make_user(n) for n in names}
    users['staff'] = make_user('staff', is_staff=True)
    return users


@pytest.fixture
def page(people):
    page = Page.objects.create(name='Shop', username='shop', created_by=people['creator'])
    PageAdmin.objects.create(page=page, user=people['creator'], role='admin')
    PageAdmin.objects.create(page=page, user=people['coadmin'], role='admin')
    PageAdmin.objects.create(page=page, user=people['editor'], role='editor')
    PageAdmin.objects.create(page=page, user=people['analyst'], role='analyst')
    for name in ('follower', 'blocked'):
        PageFollow.objects.create(page=page, user=people[name])
    Block.objects.create(blocker=people['creator'], blocked=people['blocked'])
    return page


def _jpeg(exif=True):
    img = Image.new('RGB', (12, 12), 'green')
    data = Image.Exif()
    data[0x010F] = 'SpyCam'
    buf = io.BytesIO()
    img.save(buf, format='JPEG', **({'exif': data} if exif else {}))
    return buf.getvalue()


class TestAnonymous:
    def test_everything_requires_auth(self, page):
        c = APIClient()
        for name in ('detail', 'followers', 'admins'):
            assert c.get(url(name, page)).status_code == 401
        for name in ('follow', 'admins', 'remove-admin', 'verify'):
            assert c.post(url(name, page), {}).status_code == 401
        assert c.patch(url('detail', page), {'name': 'x'}, format='json').status_code == 401


class TestEditing:
    def test_only_admins_edit(self, people, page):
        for actor in ('editor', 'analyst', 'follower', 'stranger', 'blocked'):
            r = client_for(people[actor]).patch(url('detail', page), {'name': 'Owned'}, format='json')
            assert r.status_code == 403, actor
        r = client_for(people['coadmin']).patch(url('detail', page), {
            'name': 'Shop & Co', 'description': 'We sell things', 'category': 'business',
            'website': 'https://shop.example.com', 'email': 'hi@shop.example.com', 'phone': '+27 11 000 0000',
        }, format='json')
        assert r.status_code == 200, r.data
        page.refresh_from_db()
        assert (page.name, page.category, page.website) == ('Shop & Co', 'business', 'https://shop.example.com')

    def test_admin_cannot_self_verify_or_touch_counters(self, people, page):
        client_for(people['creator']).patch(url('detail', page), {
            'is_verified': True, 'followers_count': 10**6, 'created_by': people['stranger'].id,
        }, format='json')
        page.refresh_from_db()
        assert page.is_verified is False
        assert page.followers_count != 10**6 and page.created_by_id == people['creator'].id

    def test_bad_website_and_duplicate_username_rejected(self, people, page):
        Page.objects.create(name='Other', username='taken-name')
        c = client_for(people['creator'])
        assert c.patch(url('detail', page), {'website': 'javascript:alert(1)'}, format='json').status_code == 400
        assert c.patch(url('detail', page), {'username': 'taken-name'}, format='json').status_code == 400
        assert c.patch(url('detail', page), {'username': 'shop'}, format='json').status_code == 200

    def test_avatar_and_cover_sanitised(self, people, page):
        files = {
            'avatar': SimpleUploadedFile('owner-face.jpg', _jpeg(), content_type='image/jpeg'),
            'cover_photo': SimpleUploadedFile('storefront.jpg', _jpeg(), content_type='image/jpeg'),
        }
        r = client_for(people['creator']).patch(url('detail', page), files, format='multipart')
        assert r.status_code == 200, r.data
        page.refresh_from_db()
        for field in (page.avatar, page.cover_photo):
            assert 'owner-face' not in field.name and 'storefront' not in field.name
            with field.open('rb') as fh:
                assert not Image.open(fh).getexif()

    def test_non_image_upload_rejected(self, people, page):
        upload = SimpleUploadedFile('a.png', b'<svg onload=alert(1)>', content_type='image/png')
        r = client_for(people['creator']).patch(url('detail', page), {'avatar': upload}, format='multipart')
        assert r.status_code == 400

    def test_only_admins_delete(self, people, page):
        for actor in ('editor', 'analyst', 'stranger'):
            assert client_for(people[actor]).delete(url('detail', page)).status_code == 403
        assert Page.objects.filter(pk=page.pk).exists()

    def test_my_role(self, people, page):
        assert client_for(people['creator']).get(url('detail', page)).data['my_role'] == 'admin'
        assert client_for(people['editor']).get(url('detail', page)).data['my_role'] == 'editor'
        assert client_for(people['stranger']).get(url('detail', page)).data['my_role'] is None


class TestVerification:
    def test_only_staff_verify(self, people, page):
        for actor in ('creator', 'coadmin', 'editor', 'stranger'):
            r = client_for(people[actor]).post(url('verify', page), {'is_verified': True}, format='json')
            assert r.status_code == 403, actor
        page.refresh_from_db()
        assert page.is_verified is False
        staff = client_for(people['staff'])
        assert staff.post(url('verify', page), {'is_verified': True}, format='json').data == {'is_verified': True}
        page.refresh_from_db()
        assert page.is_verified is True
        staff.post(url('verify', page), {'is_verified': False}, format='json')
        page.refresh_from_db()
        assert page.is_verified is False

    def test_admin_action(self, people, page):
        from django.contrib.admin.sites import site
        from pages.admin import PageModelAdmin
        PageModelAdmin(Page, site).mark_verified(None, Page.objects.filter(pk=page.pk))
        page.refresh_from_db()
        assert page.is_verified is True


class TestRoles:
    def test_team_list_visible_to_team_only(self, people, page):
        for actor in ('creator', 'editor', 'analyst'):
            assert client_for(people[actor]).get(url('admins', page)).status_code == 200
        for actor in ('follower', 'stranger', 'staff'):
            assert client_for(people[actor]).get(url('admins', page)).status_code == 403

    def test_only_admins_add_or_change_roles(self, people, page):
        for actor in ('editor', 'analyst', 'stranger'):
            r = client_for(people[actor]).post(url('admins', page), {'user_id': people[actor].id, 'role': 'admin'})
            assert r.status_code == 403, actor
        assert PageAdmin.objects.get(page=page, user=people['editor']).role == 'editor'
        assert not PageAdmin.objects.filter(page=page, user=people['stranger']).exists()

    def test_admin_adds_editor_and_they_can_post_as_page(self, people, page):
        r = client_for(people['coadmin']).post(url('admins', page), {'user_id': people['follower'].id, 'role': 'editor'})
        assert r.status_code == 201
        n = Notification.objects.get(recipient=people['follower'])
        assert n.extra == {'kind': 'page_role', 'page_id': page.id, 'role': 'editor'}
        r = client_for(people['follower']).post(reverse('post-list'), {'content': 'news', 'page': page.id})
        assert r.status_code == 201

    def test_cannot_add_blocked_user_or_bad_role(self, people, page):
        c = client_for(people['creator'])
        assert c.post(url('admins', page), {'user_id': people['blocked'].id, 'role': 'editor'}).status_code == 403
        assert c.post(url('admins', page), {'user_id': people['follower'].id, 'role': 'owner'}).status_code == 400
        assert c.post(url('admins', page), {'user_id': 'x', 'role': 'editor'}).status_code == 400

    def test_creator_cannot_be_demoted_or_removed(self, people, page):
        c = client_for(people['coadmin'])
        assert c.post(url('admins', page), {'user_id': people['creator'].id, 'role': 'analyst'}).status_code == 400
        assert c.post(url('remove-admin', page), {'user_id': people['creator'].id}).status_code == 400
        assert PageAdmin.objects.get(page=page, user=people['creator']).role == 'admin'

    def test_last_admin_rule_when_creator_is_gone(self, people, page):
        Page.objects.filter(pk=page.pk).update(created_by=None)
        PageAdmin.objects.filter(page=page, user=people['creator']).delete()
        c = client_for(people['coadmin'])
        assert c.post(url('admins', page), {'user_id': people['coadmin'].id, 'role': 'editor'}).status_code == 400
        assert c.post(url('remove-admin', page), {'user_id': people['coadmin'].id}).status_code == 400
        c.post(url('admins', page), {'user_id': people['editor'].id, 'role': 'admin'})
        assert c.post(url('remove-admin', page), {'user_id': people['coadmin'].id}).status_code == 200

    def test_remove_admin_rules(self, people, page):
        # Non-admins can't remove others but can leave themselves.
        r = client_for(people['editor']).post(url('remove-admin', page), {'user_id': people['analyst'].id})
        assert r.status_code == 403
        r = client_for(people['analyst']).post(url('remove-admin', page), {'user_id': people['analyst'].id})
        assert r.status_code == 200
        r = client_for(people['coadmin']).post(url('remove-admin', page), {'user_id': people['editor'].id})
        assert r.status_code == 200
        assert set(page.admins.values_list('user__username', flat=True)) == {'creator', 'coadmin'}

    def test_removed_editor_cannot_post_as_page(self, people, page):
        client_for(people['creator']).post(url('remove-admin', page), {'user_id': people['editor'].id})
        r = client_for(people['editor']).post(reverse('post-list'), {'content': 'x', 'page': page.id})
        assert r.status_code == 400


class TestFollowers:
    def test_followers_list_respects_blocks(self, people, page):
        ids = {u['id'] for u in client_for(people['creator']).get(url('followers', page)).data['results']}
        assert ids == {people['follower'].id}
        ids = {u['id'] for u in client_for(people['stranger']).get(url('followers', page)).data['results']}
        assert ids == {people['follower'].id, people['blocked'].id}

    def test_followers_hide_private_fields(self, people, page):
        rows = client_for(people['stranger']).get(url('followers', page)).data['results']
        for row in rows:
            assert 'email' not in row and 'privacy_messages' not in row

    def test_follow_unfollow_still_works(self, people, page):
        c = client_for(people['stranger'])
        assert c.post(url('follow', page)).data['following'] is True
        page.refresh_from_db()
        assert page.followers_count == 3
        assert c.post(url('unfollow', page)).data['following'] is False


class TestPagePosts:
    def test_page_id_filter_respects_visibility(self, people, page):
        public = Post.objects.create(author=people['editor'], content='launch', page=page)
        private = Post.objects.create(author=people['editor'], content='draft', page=page, privacy='private')
        Post.objects.create(author=people['editor'], content='personal')
        r = client_for(people['stranger']).get(reverse('post-list') + f'?page_id={page.id}')
        assert [p['id'] for p in r.data['results']] == [public.id]
        assert private.id not in [p['id'] for p in r.data['results']]
