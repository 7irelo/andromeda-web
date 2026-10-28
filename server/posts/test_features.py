"""
Posts & feed features: multi-image posts, edits and revisions, comment likes,
replies, edit and delete, saved and hidden posts, hashtags, page/group
posting, the ranked and chronological feed and the new-post socket event.
"""
import io
from datetime import timedelta

import pytest
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from core.test_security import befriend, client_for, make_user
from groups.models import Group, GroupMember
from pages.models import Page, PageAdmin, PageFollow
from posts import feed
from posts.models import Comment, CommentLike, HiddenPost, Like, Post, PostMedia, PostRevision, PostTag, SavedPost
from rest_framework.test import APIClient
from users.models import Block


@pytest.fixture
def alice(db):
    return make_user('alice', first_name='Alice')


@pytest.fixture
def bob(db):
    return make_user('bob', first_name='Bob')


@pytest.fixture
def mallory(db):
    return make_user('mallory')


def _png(color='red'):
    buf = io.BytesIO()
    Image.new('RGB', (8, 8), color).save(buf, format='PNG')
    return buf.getvalue()


def _jpeg_with_exif():
    buf = io.BytesIO()
    exif = Image.Exif()
    exif[0x010F] = 'SpyCam'
    Image.new('RGB', (8, 8), 'blue').save(buf, format='JPEG', exif=exif)
    return buf.getvalue()


def detail(post, suffix=''):
    name = f'post-{suffix}' if suffix else 'post-detail'
    return reverse(name, kwargs={'pk': post.pk})


def feed_ids(client, query=''):
    r = client.get(reverse('post-list') + '?feed=true' + query)
    assert r.status_code == 200, r.data
    return [p['id'] for p in r.data['results']]


# ── Multi-image posts ────────────────────────────────────────────────────────

class TestMultiImage:
    def test_images_are_sanitized_ordered_and_renamed(self, alice):
        files = [SimpleUploadedFile(f'holiday-{i}.jpg', _jpeg_with_exif(), content_type='image/jpeg')
                 for i in range(3)]
        r = client_for(alice).post(reverse('post-list'), {'content': 'trip', 'images': files}, format='multipart')
        assert r.status_code == 201, r.data
        assert r.data['post_type'] == 'image'
        assert [m['order'] for m in r.data['media']] == [0, 1, 2]
        for media in PostMedia.objects.filter(post_id=r.data['id']):
            assert 'holiday' not in media.file.name
            with media.file.open('rb') as fh:
                assert not Image.open(fh).getexif()

    def test_too_many_images_rejected(self, alice):
        files = [SimpleUploadedFile(f'{i}.png', _png(), content_type='image/png') for i in range(11)]
        r = client_for(alice).post(reverse('post-list'), {'images': files}, format='multipart')
        assert r.status_code == 400
        assert not Post.objects.exists()

    def test_non_image_in_set_rejected(self, alice):
        files = [SimpleUploadedFile('a.png', _png(), content_type='image/png'),
                 SimpleUploadedFile('b.png', b'<?php echo 1; ?>', content_type='image/png')]
        r = client_for(alice).post(reverse('post-list'), {'images': files}, format='multipart')
        assert r.status_code == 400
        assert not PostMedia.objects.exists()

    def test_reorder_and_remove_on_edit(self, alice, mallory):
        files = [SimpleUploadedFile(f'{i}.png', _png(), content_type='image/png') for i in range(3)]
        r = client_for(alice).post(reverse('post-list'), {'images': files}, format='multipart')
        post = Post.objects.get(pk=r.data['id'])
        a, b, c = [m['id'] for m in r.data['media']]
        r = client_for(alice).patch(detail(post), {'media_order': [c, a]}, format='json')
        assert r.status_code == 200, r.data
        assert [m['id'] for m in r.data['media']] == [c, a]
        assert not PostMedia.objects.filter(id=b).exists()
        # Media ids from someone else's post can't be pulled in.
        other = Post.objects.create(author=mallory, content='x')
        foreign = PostMedia.objects.create(post=other, file='public/x.png', media_type='image')
        r = client_for(alice).patch(detail(post), {'media_order': [c, foreign.id]}, format='json')
        assert r.status_code == 400


# ── Editing and revisions ────────────────────────────────────────────────────

class TestEditAndRevisions:
    def test_edit_records_revision_and_resyncs_tags(self, alice):
        post = Post.objects.create(author=alice, content='hello #old')
        PostTag.objects.create(post=post, name='old')
        r = client_for(alice).patch(detail(post), {'content': 'hello #new'}, format='json')
        assert r.status_code == 200
        assert r.data['is_edited'] is True
        assert [t['name'] for t in r.data['tags']] == ['new']
        assert list(PostRevision.objects.filter(post=post).values_list('content', flat=True)) == ['hello #old']

    def test_privacy_only_change_is_not_marked_edited(self, alice):
        post = Post.objects.create(author=alice, content='same')
        r = client_for(alice).patch(detail(post), {'privacy': 'friends'}, format='json')
        assert r.data['is_edited'] is False
        assert not PostRevision.objects.exists()

    def test_edit_notifies_only_new_mentions(self, alice, bob, mallory, django_capture_on_commit_callbacks):
        from notifications.models import Notification
        c = client_for(alice)
        with django_capture_on_commit_callbacks(execute=True):
            r = c.post(reverse('post-list'), {'content': 'hi @bob'}, format='json')
        with django_capture_on_commit_callbacks(execute=True):
            c.patch(reverse('post-detail', kwargs={'pk': r.data['id']}), {'content': 'hi @bob and @mallory'},
                    format='json')
        recipients = sorted(Notification.objects.filter(notification_type='mention')
                            .values_list('recipient__username', flat=True))
        assert recipients == ['bob', 'mallory']

    def test_history_follows_post_visibility(self, alice, bob, mallory):
        befriend(alice, bob)
        post = Post.objects.create(author=alice, content='v2', privacy='friends')
        PostRevision.objects.create(post=post, content='v1')
        r = client_for(bob).get(detail(post, 'revisions'))
        assert r.status_code == 200 and [x['content'] for x in r.data] == ['v1']
        assert client_for(mallory).get(detail(post, 'revisions')).status_code == 404
        Block.objects.create(blocker=alice, blocked=bob)
        assert client_for(bob).get(detail(post, 'revisions')).status_code == 404
        assert APIClient().get(detail(post, 'revisions')).status_code == 401

    def test_only_author_edits(self, alice, bob):
        befriend(alice, bob)
        post = Post.objects.create(author=alice, content='mine')
        assert client_for(bob).patch(detail(post), {'content': 'x'}, format='json').status_code == 403
        assert not PostRevision.objects.exists()

    def test_cannot_move_post_out_of_group(self, alice):
        group = Group.objects.create(name='Runners', created_by=alice)
        GroupMember.objects.create(group=group, user=alice, role='admin')
        post = Post.objects.create(author=alice, content='x', group=group)
        r = client_for(alice).patch(detail(post), {'group': None}, format='json')
        assert r.status_code == 400


# ── Comments ─────────────────────────────────────────────────────────────────

class TestComments:
    @pytest.fixture
    def post(self, alice):
        return Post.objects.create(author=alice, content='p')

    def comment_url(self, comment, suffix=''):
        return reverse(f'comment-{suffix or "detail"}', kwargs={'pk': comment.pk})

    def test_like_toggle_and_flag(self, post, bob):
        comment = Comment.objects.create(post=post, author=bob, content='c')
        c = client_for(bob)
        r = c.post(self.comment_url(comment, 'like'))
        assert r.data == {'liked': True, 'likes_count': 1}
        listed = c.get(detail(post, 'comments')).data
        assert listed[0]['liked'] is True and listed[0]['likes_count'] == 1
        assert c.post(self.comment_url(comment, 'like')).data == {'liked': False, 'likes_count': 0}

    def test_stranger_cannot_like_comment_on_invisible_post(self, alice, mallory):
        post = Post.objects.create(author=alice, content='p', privacy='private')
        comment = Comment.objects.create(post=post, author=alice, content='c')
        assert client_for(mallory).post(self.comment_url(comment, 'like')).status_code == 404
        assert not CommentLike.objects.exists()

    def test_blocked_users_comments_are_unreachable(self, post, alice, mallory):
        comment = Comment.objects.create(post=post, author=mallory, content='c')
        Block.objects.create(blocker=alice, blocked=mallory)
        c = client_for(alice)
        assert c.post(self.comment_url(comment, 'like')).status_code == 404
        r = c.post(detail(post, 'comments'), {'content': 'reply', 'parent': comment.id})
        assert r.status_code == 400

    def test_replies_nest_one_level(self, post, alice, bob):
        top = Comment.objects.create(post=post, author=alice, content='top')
        reply = Comment.objects.create(post=post, author=bob, content='reply', parent=top)
        r = client_for(alice).post(detail(post, 'comments'), {'content': 'deeper', 'parent': reply.id})
        assert r.status_code == 201
        assert r.data['parent'] == top.id
        listed = client_for(alice).get(detail(post, 'comments')).data
        assert len(listed) == 1 and [x['content'] for x in listed[0]['replies']] == ['reply', 'deeper']

    def test_reply_must_be_on_same_post(self, post, alice):
        other = Post.objects.create(author=alice, content='other')
        foreign = Comment.objects.create(post=other, author=alice, content='x')
        r = client_for(alice).post(detail(post, 'comments'), {'content': 'r', 'parent': foreign.id})
        assert r.status_code == 400

    def test_author_edits_others_cannot(self, post, alice, bob):
        comment = Comment.objects.create(post=post, author=bob, content='orig')
        r = client_for(bob).patch(self.comment_url(comment), {'content': 'fixed'}, format='json')
        assert r.status_code == 200 and r.data['is_edited'] is True
        # The post's author can delete but not rewrite other people's comments.
        assert client_for(alice).patch(self.comment_url(comment), {'content': 'x'}, format='json').status_code == 403
        comment.refresh_from_db()
        assert comment.content == 'fixed'

    def test_edit_cannot_move_comment(self, post, alice, bob):
        other = Post.objects.create(author=alice, content='other')
        comment = Comment.objects.create(post=post, author=bob, content='c')
        client_for(bob).patch(self.comment_url(comment), {'post': other.id, 'parent': None}, format='json')
        comment.refresh_from_db()
        assert comment.post_id == post.id

    def test_delete_rules(self, post, alice, bob, mallory):
        befriend(alice, bob)
        by_bob = Comment.objects.create(post=post, author=bob, content='b')
        by_mallory = Comment.objects.create(post=post, author=mallory, content='m')
        # A third party who can see the post cannot delete others' comments.
        assert client_for(bob).delete(self.comment_url(by_mallory)).status_code == 403
        assert client_for(mallory).delete(self.comment_url(by_bob)).status_code == 403
        # Authors can delete their own; post authors can delete any on their post.
        assert client_for(mallory).delete(self.comment_url(by_mallory)).status_code == 204
        assert client_for(alice).delete(self.comment_url(by_bob)).status_code == 204
        post.refresh_from_db()
        assert post.comments_count == 0

    def test_group_moderators_can_delete(self, alice, bob, mallory):
        group = Group.objects.create(name='Runners', created_by=alice)
        GroupMember.objects.create(group=group, user=alice, role='member')
        GroupMember.objects.create(group=group, user=bob, role='moderator')
        GroupMember.objects.create(group=group, user=mallory, role='member')
        post = Post.objects.create(author=alice, content='p', group=group)
        first = Comment.objects.create(post=post, author=mallory, content='spam')
        second = Comment.objects.create(post=post, author=alice, content='ok')
        assert client_for(bob).get(detail(post, 'comments')).data[0]['can_delete'] is True
        assert client_for(bob).delete(self.comment_url(first)).status_code == 204
        assert client_for(mallory).delete(self.comment_url(second)).status_code == 403

    def test_page_admins_can_delete_on_page_posts(self, alice, bob, mallory):
        page = Page.objects.create(name='Shop', username='shop', created_by=bob)
        PageAdmin.objects.create(page=page, user=alice, role='editor')
        post = Post.objects.create(author=alice, content='p', page=page)
        comment = Comment.objects.create(post=post, author=mallory, content='spam')
        assert client_for(bob).delete(self.comment_url(comment)).status_code == 204

    def test_no_comment_listing_endpoint(self, alice):
        assert client_for(alice).get('/api/posts/comments/').status_code in (404, 405)

    def test_anonymous_cannot_touch_comments(self, post, alice):
        comment = Comment.objects.create(post=post, author=alice, content='c')
        anon = APIClient()
        assert anon.get(self.comment_url(comment)).status_code == 401
        assert anon.post(self.comment_url(comment, 'like')).status_code == 401
        assert anon.delete(self.comment_url(comment)).status_code == 401


# ── Saved and hidden posts ───────────────────────────────────────────────────

class TestSavedAndHidden:
    def test_save_list_and_unsave(self, alice, bob):
        first = Post.objects.create(author=alice, content='1')
        second = Post.objects.create(author=alice, content='2')
        c = client_for(bob)
        assert c.post(detail(first, 'bookmark')).data == {'saved': True}
        assert c.post(detail(second, 'bookmark')).data == {'saved': True}
        r = c.get(reverse('post-saved'))
        assert [p['id'] for p in r.data['results']] == [second.id, first.id]
        assert all(p['is_saved'] for p in r.data['results'])
        assert c.delete(detail(first, 'bookmark')).data == {'saved': False}
        assert [p['id'] for p in c.get(reverse('post-saved')).data['results']] == [second.id]

    def test_cannot_save_invisible_post_and_saved_list_rechecks(self, alice, bob, mallory):
        private = Post.objects.create(author=alice, content='p', privacy='private')
        assert client_for(mallory).post(detail(private, 'bookmark')).status_code == 404
        post = Post.objects.create(author=alice, content='later private')
        SavedPost.objects.create(user=bob, post=post)
        post.privacy = 'private'
        post.save()
        assert client_for(bob).get(reverse('post-saved')).data['results'] == []

    def test_saved_list_is_per_user(self, alice, bob, mallory):
        post = Post.objects.create(author=alice, content='x')
        SavedPost.objects.create(user=bob, post=post)
        assert client_for(mallory).get(reverse('post-saved')).data['results'] == []
        assert APIClient().get(reverse('post-saved')).status_code == 401

    def test_saved_list_hides_blocked_authors(self, alice, bob):
        post = Post.objects.create(author=alice, content='x')
        SavedPost.objects.create(user=bob, post=post)
        Block.objects.create(blocker=alice, blocked=bob)
        assert client_for(bob).get(reverse('post-saved')).data['results'] == []

    def test_hide_removes_from_own_feed_only(self, alice, bob, mallory):
        befriend(alice, bob)
        befriend(alice, mallory)
        post = Post.objects.create(author=alice, content='x')
        assert client_for(bob).post(detail(post, 'hide')).data == {'hidden': True}
        assert post.id not in feed_ids(client_for(bob))
        assert post.id not in feed_ids(client_for(bob), '&sort=latest')
        assert post.id in feed_ids(client_for(mallory))
        # Still reachable directly, and the hide can be undone.
        assert client_for(bob).get(detail(post)).status_code == 200
        client_for(bob).delete(detail(post, 'hide'))
        assert post.id in feed_ids(client_for(bob))

    def test_cannot_hide_invisible_post(self, alice, mallory):
        private = Post.objects.create(author=alice, content='p', privacy='private')
        assert client_for(mallory).post(detail(private, 'hide')).status_code == 404
        assert not HiddenPost.objects.exists()


# ── Hashtags ─────────────────────────────────────────────────────────────────

class TestHashtags:
    def test_tag_listing_respects_visibility(self, alice, mallory):
        r = client_for(alice).post(reverse('post-list'), {'content': 'Run #Joburg'}, format='json')
        public_id = r.data['id']
        r = client_for(alice).post(reverse('post-list'), {'content': 'Me #joburg', 'privacy': 'private'},
                                   format='json')
        ids = [p['id'] for p in client_for(mallory).get(reverse('post-list') + '?tag=joburg').data['results']]
        assert ids == [public_id]
        Block.objects.create(blocker=mallory, blocked=alice)
        assert client_for(mallory).get(reverse('post-list') + '?tag=%23Joburg').data['results'] == []


# ── Posting as a page / into a group ─────────────────────────────────────────

class TestPageAndGroupPosting:
    def test_page_admins_and_editors_can_post_as_page(self, alice, bob, mallory):
        page = Page.objects.create(name='Shop', username='shop', created_by=alice)
        PageAdmin.objects.create(page=page, user=bob, role='editor')
        PageAdmin.objects.create(page=page, user=mallory, role='analyst')
        r = client_for(bob).post(reverse('post-list'), {'content': 'sale', 'page': page.id}, format='json')
        assert r.status_code == 201 and r.data['page_data']['name'] == 'Shop'
        r = client_for(mallory).post(reverse('post-list'), {'content': 'x', 'page': page.id}, format='json')
        assert r.status_code == 400

    def test_cannot_move_post_onto_a_page_you_dont_run(self, alice, mallory):
        page = Page.objects.create(name='Shop', username='shop', created_by=alice)
        post = Post.objects.create(author=mallory, content='x')
        r = client_for(mallory).patch(detail(post), {'page': page.id}, format='json')
        assert r.status_code == 400
        post.refresh_from_db()
        assert post.page_id is None

    def test_group_members_only(self, alice, mallory):
        group = Group.objects.create(name='Runners', privacy='private', created_by=alice)
        GroupMember.objects.create(group=group, user=alice, role='admin')
        r = client_for(alice).post(reverse('post-list'), {'content': 'hi', 'group': group.id}, format='json')
        assert r.status_code == 201 and r.data['group_data'] == {'id': group.id, 'name': 'Runners'}
        r = client_for(mallory).post(reverse('post-list'), {'content': 'x', 'group': group.id}, format='json')
        assert r.status_code == 400

    def test_cannot_move_own_post_into_group_without_membership(self, alice, mallory):
        group = Group.objects.create(name='Runners', created_by=alice)
        post = Post.objects.create(author=mallory, content='x')
        r = client_for(mallory).patch(detail(post), {'group': group.id}, format='json')
        assert r.status_code == 400


# ── Feed ─────────────────────────────────────────────────────────────────────

class TestFeed:
    def test_sources_friends_groups_pages_not_strangers(self, alice, bob, mallory):
        carol = make_user('carol')
        befriend(alice, bob)
        group = Group.objects.create(name='Runners', created_by=carol)
        GroupMember.objects.create(group=group, user=alice)
        GroupMember.objects.create(group=group, user=carol)
        page = Page.objects.create(name='Shop', username='shop', created_by=carol)
        PageFollow.objects.create(page=page, user=alice)
        own = Post.objects.create(author=alice, content='own')
        friend = Post.objects.create(author=bob, content='friend', privacy='friends')
        in_group = Post.objects.create(author=carol, content='group', group=group)
        on_page = Post.objects.create(author=carol, content='page', page=page)
        stranger = Post.objects.create(author=mallory, content='stranger')
        for sort in ('', '&sort=latest'):
            ids = set(feed_ids(client_for(alice), sort))
            assert {own.id, friend.id, in_group.id, on_page.id} <= ids
            assert stranger.id not in ids

    def test_feed_never_leaks_invisible_posts(self, alice, bob):
        befriend(alice, bob)
        private = Post.objects.create(author=bob, content='p', privacy='private')
        removed = Post.objects.create(author=bob, content='r', moderation_status='removed')
        secret = Group.objects.create(name='S', privacy='secret', created_by=bob)
        GroupMember.objects.create(group=secret, user=bob)
        in_secret = Post.objects.create(author=bob, content='s', group=secret)
        for sort in ('', '&sort=latest'):
            ids = set(feed_ids(client_for(alice), sort))
            assert not ids & {private.id, removed.id, in_secret.id}

    def test_blocked_friend_disappears(self, alice, bob):
        befriend(alice, bob)
        post = Post.objects.create(author=bob, content='x')
        Block.objects.create(blocker=bob, blocked=alice)
        assert post.id not in feed_ids(client_for(alice))

    def test_anonymous_feed_rejected(self, db):
        assert APIClient().get(reverse('post-list') + '?feed=true').status_code == 401

    def test_latest_cursor_is_stable_under_inserts(self, alice):
        posts = [Post.objects.create(author=alice, content=str(i)) for i in range(feed.PAGE_SIZE + 5)]
        c = client_for(alice)
        first = c.get(reverse('post-list') + '?feed=true&sort=latest').data
        assert len(first['results']) == feed.PAGE_SIZE and first['next_cursor']
        Post.objects.create(author=alice, content='brand new')
        second = c.get(reverse('post-list') + f'?feed=true&sort=latest&cursor={first["next_cursor"]}').data
        seen = [p['id'] for p in first['results'] + second['results']]
        assert len(seen) == len(set(seen)) == len(posts)
        assert second['next_cursor'] is None

    def test_top_cursor_is_stable_under_inserts(self, alice):
        posts = [Post.objects.create(author=alice, content=str(i)) for i in range(feed.PAGE_SIZE + 5)]
        c = client_for(alice)
        first = c.get(reverse('post-list') + '?feed=true').data
        Post.objects.create(author=alice, content='brand new')
        second = c.get(reverse('post-list') + f'?feed=true&cursor={first["next_cursor"]}').data
        seen = [p['id'] for p in first['results'] + second['results']]
        assert len(seen) == len(set(seen)) == len(posts)

    def test_top_continues_chronologically_past_the_window(self, alice, monkeypatch):
        monkeypatch.setattr(feed, 'CANDIDATE_WINDOW', 3)
        monkeypatch.setattr(feed, 'PAGE_SIZE', 2)
        posts = [Post.objects.create(author=alice, content=str(i)) for i in range(6)]
        c = client_for(alice)
        seen, cursor = [], ''
        for _ in range(10):
            data = c.get(reverse('post-list') + f'?feed=true&cursor={cursor}').data
            seen += [p['id'] for p in data['results']]
            cursor = data['next_cursor']
            if not cursor:
                break
        assert sorted(seen) == sorted(p.id for p in posts)

    def test_bad_cursor_and_sort(self, alice):
        c = client_for(alice)
        assert c.get(reverse('post-list') + '?feed=true&cursor=not-a-cursor').status_code == 400
        assert c.get(reverse('post-list') + '?feed=true&sort=evil').status_code == 400

    def test_ranking_prefers_affinity_and_explains(self, alice, bob, mallory):
        carol = make_user('carol', first_name='Thandi')
        befriend(alice, bob)
        befriend(alice, carol)
        # Alice often likes Thandi's posts.
        for i in range(3):
            Like.objects.create(user=alice, post=Post.objects.create(author=carol, content=f'old {i}'))
        older = timezone.now() - timedelta(hours=2)
        liked_author = Post.objects.create(author=carol, content='from thandi')
        plain = Post.objects.create(author=bob, content='from bob')
        Post.objects.filter(pk=liked_author.pk).update(created_at=older)
        data = client_for(alice).get(reverse('post-list') + '?feed=true').data['results']
        order = [p['id'] for p in data]
        assert order.index(liked_author.id) < order.index(plain.id)
        reasons = {p['id']: p['reason'] for p in data}
        assert reasons[liked_author.id] == "Because you often like Thandi's posts"
        assert reasons[plain.id] == 'New from a friend'

    def test_popular_in_group_reason(self, alice, bob):
        group = Group.objects.create(name='Joburg Runners', created_by=bob)
        GroupMember.objects.create(group=group, user=alice)
        GroupMember.objects.create(group=group, user=bob)
        post = Post.objects.create(author=bob, content='race day', group=group, likes_count=12)
        data = client_for(alice).get(reverse('post-list') + '?feed=true').data['results']
        assert {p['id']: p['reason'] for p in data}[post.id] == 'Popular in Joburg Runners'

    def test_feed_query_count_is_bounded(self, alice, bob, django_assert_max_num_queries):
        befriend(alice, bob)
        original = Post.objects.create(author=bob, content='orig')
        for i in range(15):
            p = Post.objects.create(author=bob, content=f'{i} #tag', shared_post=original if i % 3 == 0 else None)
            Like.objects.create(user=alice, post=p)
        c = client_for(alice)
        with django_assert_max_num_queries(25):
            r = c.get(reverse('post-list') + '?feed=true')
        assert len(r.data['results']) == 16
        assert all(p['my_reaction'] == 'like' for p in r.data['results'] if p['id'] != original.id)


# ── New-post socket event ────────────────────────────────────────────────────

class TestNewPostEvent:
    def _listen(self, user):
        layer = get_channel_layer()
        channel = async_to_sync(layer.new_channel)()
        async_to_sync(layer.group_add)(f'notifications_{user.id}', channel)
        return layer, channel

    def _drain(self, layer, channel):
        import asyncio
        out = []

        async def pull():
            while True:
                try:
                    out.append(await asyncio.wait_for(layer.receive(channel), timeout=0.05))
                except asyncio.TimeoutError:
                    return
        async_to_sync(pull)()
        return out

    def test_friends_get_ids_only(self, alice, bob, mallory, django_capture_on_commit_callbacks):
        befriend(alice, bob)
        bob_layer, bob_chan = self._listen(bob)
        mal_layer, mal_chan = self._listen(mallory)
        with django_capture_on_commit_callbacks(execute=True):
            r = client_for(alice).post(reverse('post-list'), {'content': 'secret words'}, format='json')
        events = self._drain(bob_layer, bob_chan)
        assert events == [{'type': 'feed.new_post', 'post_id': r.data['id']}]
        assert self._drain(mal_layer, mal_chan) == []

    def test_private_posts_and_blocked_friends_get_nothing(self, alice, bob):
        from posts.tasks import new_post_recipients
        befriend(alice, bob)
        private = Post.objects.create(author=alice, content='p', privacy='private')
        assert new_post_recipients(private) == set()
        public = Post.objects.create(author=alice, content='x')
        assert new_post_recipients(public) == {bob.id}
        Block.objects.create(blocker=bob, blocked=alice)
        assert new_post_recipients(public) == set()

    def test_private_group_post_only_reaches_members(self, alice, bob):
        from posts.tasks import new_post_recipients
        befriend(alice, bob)
        group = Group.objects.create(name='G', privacy='private', created_by=alice)
        GroupMember.objects.create(group=group, user=alice)
        post = Post.objects.create(author=alice, content='x', group=group)
        assert new_post_recipients(post) == set()
        GroupMember.objects.create(group=group, user=bob)
        assert new_post_recipients(post) == {bob.id}

    def test_consumer_forwards_only_the_id(self):
        from notifications.consumers import NotificationConsumer
        sent = []
        consumer = NotificationConsumer()

        async def fake_send(text_data=None, bytes_data=None):
            sent.append(text_data)
        consumer.send = fake_send
        async_to_sync(consumer.feed_new_post)({'type': 'feed.new_post', 'post_id': 7, 'content': 'leak'})
        async_to_sync(consumer.feed_new_post)({'type': 'feed.new_post', 'post_id': '7; drop'})
        assert sent == ['{"type": "feed.new_post", "post_id": 7}']
