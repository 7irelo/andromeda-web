import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

from feedcache import candidates as fc
from feedcache.store import CacheStore, RedisStore, reset_store
from pages.models import Page, PageFollow
from posts.feed import feed_queryset
from posts.models import Post
from users.models import Block, FriendRequest

User = get_user_model()


@pytest.fixture(autouse=True)
def fresh_cache(settings):
    settings.FEEDCACHE_ENABLED = True
    settings.FEEDCACHE_FANOUT_THRESHOLD = 10
    cache.clear()
    reset_store()
    yield
    cache.clear()
    reset_store()


def _user(name):
    return User.objects.create_user(username=name, password='pass-1234567', email=f'{name}@example.com')


def _friends(a, b):
    FriendRequest.objects.create(sender=a, receiver=b, status=FriendRequest.STATUS_ACCEPTED)


@pytest.fixture
def people(db):
    ana, ben, cy = _user('ana'), _user('ben'), _user('cy')
    _friends(ana, ben)
    return ana, ben, cy


def _inbox(user):
    return CacheStore().read(user.id, 1000)


class TestReadPath:
    def test_disabled_or_anonymous_means_no_cache(self, people, settings):
        from django.contrib.auth.models import AnonymousUser
        assert fc.candidates(AnonymousUser()) is None
        settings.FEEDCACHE_ENABLED = False
        assert fc.candidates(people[0]) is None

    def test_cold_inbox_is_built_from_the_database(self, people):
        ana, ben, cy = people
        mine = Post.objects.create(author=ana, content='mine')
        friend = Post.objects.create(author=ben, content='friend')
        Post.objects.create(author=cy, content='stranger')  # public, but not a feed source
        assert _inbox(ana) is None
        assert fc.candidates(ana) == [friend.id, mine.id]
        assert _inbox(ana) == [friend.id, mine.id]

    def test_empty_feed_is_cached_as_empty_not_cold(self, people):
        _, _, cy = people
        assert fc.candidates(cy) == []
        assert _inbox(cy) == []

    def test_cache_errors_fall_back_to_the_database(self, people, monkeypatch):
        def boom(*a, **k):
            raise ConnectionError('redis down')
        monkeypatch.setattr(CacheStore, 'read', boom)
        assert fc.candidates(people[0]) is None

    def test_candidates_are_still_filtered_by_visibility(self, people):
        ana, ben, cy = people
        secret = Post.objects.create(author=cy, content='only me', privacy=Post.PRIVACY_PRIVATE)
        fc.candidates(ana)
        # Even a poisoned inbox can't widen what the feed shows.
        CacheStore().push([ana.id], secret.id)
        ids = fc.candidates(ana)
        assert secret.id in ids
        assert not feed_queryset(ana).filter(id__in=ids, id=secret.id).exists()


class TestFanOut:
    def test_new_post_is_pushed_to_warm_inboxes_only(self, people, django_capture_on_commit_callbacks):
        ana, ben, cy = people
        fc.candidates(ben)  # ben's inbox is warm, cy's stays cold
        with django_capture_on_commit_callbacks(execute=True):
            post = Post.objects.create(author=ana, content='hello')
        assert _inbox(ben) == [post.id]
        assert _inbox(cy) is None

    def test_private_posts_reach_only_the_author(self, people, django_capture_on_commit_callbacks):
        ana, ben, _ = people
        fc.candidates(ana)
        fc.candidates(ben)
        with django_capture_on_commit_callbacks(execute=True):
            post = Post.objects.create(author=ana, content='diary', privacy=Post.PRIVACY_PRIVATE)
        assert _inbox(ana) == [post.id]
        assert _inbox(ben) == []

    def test_popular_authors_are_pulled_on_read(self, people, settings, django_capture_on_commit_callbacks):
        ana, ben, _ = people
        fc.candidates(ben)
        User.objects.filter(pk=ana.pk).update(friends_count=50)  # above the threshold of 10
        with django_capture_on_commit_callbacks(execute=True):
            post = Post.objects.create(author=ana, content='to the masses')
        assert _inbox(ben) == []          # not pushed...
        assert fc.candidates(ben) == [post.id]  # ...but merged in when read

    def test_large_pages_are_pulled_on_read(self, people, django_capture_on_commit_callbacks):
        ana, ben, cy = people
        page = Page.objects.create(name='Big', username='bigpage', created_by=cy, followers_count=500)
        PageFollow.objects.create(page=page, user=ben)
        fc.candidates(ben)
        with django_capture_on_commit_callbacks(execute=True):
            post = Post.objects.create(author=cy, page=page, content='news')
        assert post.id not in _inbox(ben)
        assert post.id in fc.candidates(ben)

    def test_small_pages_are_pushed(self, people, django_capture_on_commit_callbacks):
        ana, ben, cy = people
        page = Page.objects.create(name='Small', username='smallpage', created_by=cy, followers_count=1)
        PageFollow.objects.create(page=page, user=ben)
        fc.candidates(ben)
        with django_capture_on_commit_callbacks(execute=True):
            post = Post.objects.create(author=cy, page=page, content='news')
        assert _inbox(ben) == [post.id]


class TestInvalidation:
    def test_delete_retracts_the_post(self, people, django_capture_on_commit_callbacks):
        ana, ben, _ = people
        post = Post.objects.create(author=ana, content='oops')
        fc.candidates(ben)
        assert _inbox(ben) == [post.id]
        with django_capture_on_commit_callbacks(execute=True):
            post.delete()
        assert _inbox(ben) == []

    def test_privacy_change_moves_the_post(self, people, django_capture_on_commit_callbacks):
        ana, ben, _ = people
        post = Post.objects.create(author=ana, content='hmm')
        fc.candidates(ben)
        with django_capture_on_commit_callbacks(execute=True):
            post.privacy = Post.PRIVACY_PRIVATE
            post.save()
        assert _inbox(ben) == []
        with django_capture_on_commit_callbacks(execute=True):
            post.privacy = Post.PRIVACY_FRIENDS
            post.save()
        assert _inbox(ben) == [post.id]

    def test_unrelated_edits_leave_inboxes_alone(self, people, django_capture_on_commit_callbacks, monkeypatch):
        ana, ben, _ = people
        post = Post.objects.create(author=ana, content='v1')
        calls = []
        monkeypatch.setattr(fc, 'retract', lambda p: calls.append(p.id))
        with django_capture_on_commit_callbacks(execute=True):
            post.content = 'v2'
            post.save()
        assert calls == []

    def test_block_drops_both_inboxes(self, people, django_capture_on_commit_callbacks):
        ana, ben, _ = people
        fc.candidates(ana)
        fc.candidates(ben)
        with django_capture_on_commit_callbacks(execute=True):
            Block.objects.create(blocker=ana, blocked=ben)
        assert _inbox(ana) is None and _inbox(ben) is None

    def test_new_friendship_drops_both_inboxes(self, people, django_capture_on_commit_callbacks):
        ana, ben, cy = people
        fc.candidates(ana)
        fc.candidates(cy)
        with django_capture_on_commit_callbacks(execute=True):
            _friends(cy, ana)
        assert _inbox(ana) is None and _inbox(cy) is None

    def test_unfollowing_a_page_drops_the_inbox(self, people, django_capture_on_commit_callbacks):
        ana, ben, cy = people
        page = Page.objects.create(name='P', username='ppage', created_by=cy)
        follow = PageFollow.objects.create(page=page, user=ben)
        fc.candidates(ben)
        with django_capture_on_commit_callbacks(execute=True):
            follow.delete()
        assert _inbox(ben) is None


class FakeRedis:
    """Just the list commands RedisStore uses."""

    def __init__(self):
        self.data = {}

    def pipeline(self, transaction=True):
        return FakePipeline(self)

    def delete(self, *keys):
        for k in keys:
            self.data.pop(k, None)


class FakePipeline:
    def __init__(self, r):
        self.r, self.ops = r, []

    def __getattr__(self, name):
        return lambda *a: self.ops.append((name, a))

    def execute(self):
        d, out = self.r.data, []
        for name, a in self.ops:
            if name == 'exists':
                out.append(int(a[0] in d))
            elif name == 'lrange':
                items = d.get(a[0], [])
                out.append([str(v).encode() for v in items[a[1]:a[2] + 1]])
            elif name == 'delete':
                out.append(int(d.pop(a[0], None) is not None))
            elif name == 'rpush':
                d.setdefault(a[0], []).extend(a[1:])
                out.append(len(d[a[0]]))
            elif name == 'lpushx':
                if a[0] in d:
                    d[a[0]].insert(0, a[1])
                out.append(len(d.get(a[0], [])))
            elif name == 'ltrim':
                if a[0] in d:
                    d[a[0]] = d[a[0]][a[1]:a[2] + 1]
                out.append(True)
            elif name == 'lrem':
                if a[0] in d:
                    d[a[0]] = [v for v in d[a[0]] if v != a[2]]
                out.append(1)
            else:
                out.append(True)
        return out


class TestRedisStore:
    def test_cold_build_push_trim_remove(self, settings):
        settings.FEEDCACHE_MAX_ITEMS = 3
        store = RedisStore(FakeRedis(), 'andromeda')
        assert store.read(1, 10) is None
        store.push([1], 99)                 # LPUSHX: a cold inbox stays cold
        assert store.read(1, 10) is None
        store.build(1, [])
        assert store.read(1, 10) == []      # built but empty: the sentinel tells them apart
        for pid in (5, 6, 7, 8):
            store.push([1], pid)
        assert store.read(1, 10) == [8, 7, 6]  # capped
        store.remove([1], 7)
        assert store.read(1, 10) == [8, 6]
        store.drop([1])
        assert store.read(1, 10) is None
        assert 'andromeda:feedcache:inbox:1' not in store.r.data
