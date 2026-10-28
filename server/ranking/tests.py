"""
Feed ranking: features, impressions, training, serving, the A/B readout and drift.

The privacy tests matter most: impressions are personal data, so a viewer can
only ever touch their own rows for posts they were actually served and can
still see, and only staff see aggregates.
"""
import io
import math
from datetime import timedelta

import numpy as np
import pytest
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from chats.models import ChatMember, ChatRoom, Message
from core.test_security import befriend, client_for, make_user
from groups.models import Group, GroupMember
from pages.models import Page, PageFollow
from posts import feed
from posts.models import Comment, HiddenPost, Like, Post, SavedPost
from retrieval.models import DIMS, Embedding
from users.models import Block

from . import features, impressions, model_store, serving, tasks, training
from .management.commands.ab_report import two_proportion
from .models import FeedImpression

F = features.INDEX


@pytest.fixture(autouse=True)
def _isolated(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.RANKING_MODEL_CHECK_SECONDS = 0
    model_store.reset()
    cache.clear()
    yield
    model_store.reset()


@pytest.fixture
def alice(db):
    return make_user('alice')


@pytest.fixture
def bob(db):
    return make_user('bob', first_name='Thandi')


@pytest.fixture
def mallory(db):
    return make_user('mallory')


def feed_url(extra=''):
    return reverse('post-list') + '?feed=true' + extra


def build_one(viewer, post, as_of=None):
    return features.build(viewer, features.candidates_from(Post.objects.filter(pk=post.pk)),
                          as_of or timezone.now() + timedelta(seconds=1))[0]


def synthetic_dataset(n=1500, seed=3):
    """A learnable toy problem in the real feature space, with timestamps one minute apart."""
    rng = np.random.default_rng(seed)
    X = np.zeros((n, len(features.FEATURES)))
    X[:, F['is_friend']] = rng.integers(0, 2, n)
    X[:, F['author_likes_30d']] = np.log1p(rng.poisson(1.5, n))
    X[:, F['age_hours']] = np.log1p(rng.uniform(0, 200, n))
    X[:, F['post_likes']] = np.log1p(rng.poisson(3, n))
    X[:, F['media_type']] = rng.integers(0, 4, n)
    X[:, F['author_engagement_rate']] = rng.uniform(0, 0.4, n)
    logit = -2.0 + 2.0 * X[:, F['is_friend']] + 1.5 * X[:, F['author_likes_30d']] - 0.8 * (X[:, F['age_hours']] - 4)
    y = (rng.uniform(size=n) < 1 / (1 + np.exp(-logit))).astype(int)
    start = timezone.now() - timedelta(days=5)
    t = [start + timedelta(minutes=i) for i in range(n)]
    return X, y, t


@pytest.fixture
def trained(db):
    X, y, t = synthetic_dataset()
    booster, report = training.train(X, y, t, min_rows=100)
    meta = {'version': 'test', 'feature_version': features.FEATURE_VERSION, 'features': features.FEATURES,
            'synthetic': True, **report}
    model_store.save(booster.model_to_string(num_iteration=report['best_iteration']), meta, '20260101T000000Z')
    model_store.reset()
    return report


# ── Features ─────────────────────────────────────────────────────────────────

class TestFeatures:
    def test_affinity_graph_and_context(self, alice, bob, mallory):
        carol = make_user('carol')
        befriend(alice, bob)
        befriend(alice, carol)
        befriend(bob, carol)  # carol is a mutual friend of alice and bob
        group = Group.objects.create(name='Runners', created_by=bob)
        for u in (alice, bob):
            GroupMember.objects.create(group=group, user=u)
        page = Page.objects.create(name='Shop', username='shop', created_by=bob)
        PageFollow.objects.create(page=page, user=alice)
        for i in range(3):
            Like.objects.create(user=alice, post=Post.objects.create(author=bob, content=f'old {i}'))
        Comment.objects.create(author=alice, post=Post.objects.create(author=bob, content='c'), content='hi')
        room = ChatRoom.objects.create(room_type='direct', created_by=alice)
        ChatMember.objects.create(room=room, user=alice)
        ChatMember.objects.create(room=room, user=bob)
        for _ in range(2):
            Message.objects.create(room=room, sender=bob, content='hey')

        post = Post.objects.create(author=bob, content='x', group=group, page=page, post_type='image')
        Like.objects.create(user=carol, post=post)
        Comment.objects.create(author=carol, post=post, content='nice')
        f = build_one(alice, post)
        assert f[F['is_own_post']] == 0 and f[F['is_friend']] == 1
        assert features.raw_count(f[F['author_likes_30d']]) == 3
        assert features.raw_count(f[F['author_comments_30d']]) == 1
        assert features.raw_count(f[F['author_messages_30d']]) == 2
        assert features.raw_count(f[F['shared_groups']]) == 1
        assert features.raw_count(f[F['mutual_friends']]) == 1
        assert f[F['in_member_group']] == 1 and f[F['follows_page']] == 1
        assert features.raw_count(f[F['post_likes']]) == 1 and features.raw_count(f[F['post_comments']]) == 1
        assert features.raw_count(f[F['friend_engagements']]) == 2
        assert f[F['media_type']] == features.MEDIA_TYPES['image']
        assert f[F['engagement_velocity']] == pytest.approx(math.log1p(2.0))  # 2 interactions, < 1 hour old

        stranger_post = Post.objects.create(author=mallory, content='y')
        g = build_one(alice, stranger_post)
        assert g[F['is_friend']] == 0 and g[F['author_likes_30d']] == 0 and g[F['mutual_friends']] == 0
        assert build_one(alice, Post.objects.create(author=alice, content='me'))[F['is_own_post']] == 1

    def test_mutual_friends_from_neo4j_with_sql_fallback(self, alice, bob, settings, monkeypatch):
        from neomodel import db
        carol = make_user('carol')
        befriend(alice, carol)
        befriend(bob, carol)
        settings.NEO4J_ENABLED = True
        monkeypatch.setattr(db, 'cypher_query', lambda q, p: ([[bob.id, 7]], None))
        assert features.mutual_friends(alice, {bob.id}, {carol.id}) == {bob.id: 7}

        def down(q, p):
            raise ConnectionError('neo4j down')
        monkeypatch.setattr(db, 'cypher_query', down)
        assert features.mutual_friends(alice, {bob.id}, {carol.id}) == {bob.id: 1}

    def test_features_only_see_the_past(self, alice, bob):
        befriend(alice, bob)
        post = Post.objects.create(author=bob, content='x')
        as_of = timezone.now()
        Post.objects.filter(pk=post.pk).update(created_at=as_of - timedelta(hours=3))
        Like.objects.create(user=alice, post=post)  # after as_of
        f = build_one(alice, post, as_of=as_of)
        assert f[F['post_likes']] == 0 and f[F['author_likes_30d']] == 0
        assert features.raw_count(f[F['age_hours']]) == 3

    def test_query_count_does_not_grow_with_the_window(self, alice, bob, django_assert_max_num_queries):
        befriend(alice, bob)
        authors = [make_user(f'u{i}') for i in range(30)]
        for a in authors:
            befriend(alice, a)
        for i in range(120):
            Post.objects.create(author=authors[i % 30], content=str(i))
        now = timezone.now() + timedelta(seconds=1)
        small = features.candidates_from(Post.objects.all()[:3])
        large = features.candidates_from(Post.objects.all())
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as few:
            features.build(alice, small, now)
        with CaptureQueriesContext(connection) as many:
            features.build(alice, large, now)
        assert len(many) == len(few) <= 20

    def test_interest_similarity_from_engagement_history(self, alice, bob):
        def vec(axis):
            v = [0.0] * DIMS
            v[axis] = 1.0
            return v
        liked = Post.objects.create(author=bob, content='running')
        similar = Post.objects.create(author=bob, content='more running')
        other = Post.objects.create(author=bob, content='cooking')
        for p, axis in ((liked, 0), (similar, 0), (other, 1)):
            Embedding.objects.create(kind='posts', object_id=p.id, text=p.content, content_hash='h',
                                     vector=vec(axis), model='fake')
        Like.objects.create(user=alice, post=liked)
        now = timezone.now() + timedelta(seconds=1)
        X = features.build(alice, features.candidates_from(Post.objects.filter(pk__in=[similar.pk, other.pk])
                                                            .order_by('pk')), now)
        assert X[0, F['interest_similarity']] == pytest.approx(1.0)
        assert X[1, F['interest_similarity']] == pytest.approx(0.0)
        alice.ai_opt_out = True
        assert build_one(alice, similar, now)[F['interest_similarity']] == 0

    def test_heuristic_matches_ranking_v1(self, alice, bob):
        befriend(alice, bob)
        for i in range(3):
            Like.objects.create(user=alice, post=Post.objects.create(author=bob, content=f'old {i}'))
        post = Post.objects.create(author=bob, content='x')
        Like.objects.create(user=make_user('z'), post=post)
        Post.objects.filter(pk=post.pk).update(created_at=timezone.now() - timedelta(hours=5))
        anchor = timezone.now()
        rows = [r for r in feed.candidate_window(alice, anchor) if r[0] == post.id]
        signals = feed.Signals(alice, {bob.id}, anchor)
        r = rows[0]
        v1 = feed.recency(r[4], anchor) * signals.affinity(r[1], r[2], r[3]) * feed.engagement(r[5], r[6])
        X = features.build(alice, feed.as_candidates(rows), anchor)
        assert features.heuristic_score(X)[0] == pytest.approx(v1, rel=1e-6)


# ── Impressions ──────────────────────────────────────────────────────────────

class TestImpressions:
    def test_served_page_is_logged_and_nothing_else(self, alice, bob, mallory, settings,
                                                    django_capture_on_commit_callbacks):
        befriend(alice, bob)
        settings.RANKING_FEED_RANKER_WEIGHTS = {'v1': 100, 'v2': 0}
        mine = [Post.objects.create(author=bob, content=str(i)) for i in range(feed.PAGE_SIZE + 3)]
        stranger = Post.objects.create(author=mallory, content='not in alice\'s feed')
        with django_capture_on_commit_callbacks(execute=True):
            data = client_for(alice).get(feed_url()).data
        served = [p['id'] for p in data['results']]
        rows = list(FeedImpression.objects.filter(viewer=alice).order_by('position'))
        assert [r.post_id for r in rows] == served and len(rows) == feed.PAGE_SIZE
        assert [r.position for r in rows] == list(range(feed.PAGE_SIZE))
        assert {r.variant for r in rows} == {'v1'} and {r.ranker for r in rows} == {'v1'}
        assert all(isinstance(r.features, list) and len(r.features) == len(features.FEATURES) for r in rows)
        assert not FeedImpression.objects.filter(post=stranger).exists()
        assert not FeedImpression.objects.exclude(viewer=alice).exists()
        assert len(mine) > len(rows)

        with django_capture_on_commit_callbacks(execute=True):
            client_for(alice).get(feed_url(f'&cursor={data["next_cursor"]}'))
        assert FeedImpression.objects.filter(viewer=alice, position__gte=feed.PAGE_SIZE).count() == 3

    def test_latest_feed_is_logged_outside_the_experiment(self, alice):
        Post.objects.create(author=alice, content='x')
        client_for(alice).get(feed_url('&sort=latest'))
        row = FeedImpression.objects.get(viewer=alice)
        assert row.variant == '' and row.ranker == 'latest'

    def test_rows_per_request_are_capped(self, alice):
        posts = [Post.objects.create(author=alice, content=str(i)) for i in range(impressions.MAX_PER_REQUEST + 10)]
        assert len(impressions.log_page(alice, posts, first_position=0, variant='', ranker='latest')) == \
            impressions.MAX_PER_REQUEST

    def test_logging_can_be_switched_off(self, alice, settings):
        settings.RANKING_LOG_IMPRESSIONS = False
        Post.objects.create(author=alice, content='x')
        client_for(alice).get(feed_url())
        assert not FeedImpression.objects.exists()

    def test_engagement_marks_the_impression(self, alice, bob, django_capture_on_commit_callbacks):
        befriend(alice, bob)
        posts = [Post.objects.create(author=bob, content=str(i), privacy='public') for i in range(5)]
        client_for(alice).get(feed_url())
        c = client_for(alice)
        with django_capture_on_commit_callbacks(execute=True):
            c.post(reverse('post-react', kwargs={'pk': posts[0].pk}), {'reaction': 'love'}, format='json')
            c.post(reverse('post-comments', kwargs={'pk': posts[1].pk}), {'content': 'hi'}, format='json')
            c.post(reverse('post-bookmark', kwargs={'pk': posts[2].pk}))
            c.post(reverse('post-share', kwargs={'pk': posts[3].pk}), {}, format='json')
        engaged = set(FeedImpression.objects.filter(viewer=alice, engaged=True).values_list('post_id', flat=True))
        assert engaged == {p.id for p in posts[:4]}
        assert FeedImpression.objects.filter(engaged=True, engaged_at__isnull=True).count() == 0

    def test_late_or_foreign_engagement_does_not_count(self, alice, bob, mallory, django_capture_on_commit_callbacks):
        post = Post.objects.create(author=bob, content='x')
        old = FeedImpression.objects.create(viewer=alice, post=post, position=0, ranker='v1',
                                            served_at=timezone.now() - timedelta(hours=25))
        with django_capture_on_commit_callbacks(execute=True):
            Like.objects.create(user=alice, post=post)
            SavedPost.objects.create(user=mallory, post=post)
        old.refresh_from_db()
        assert not old.engaged
        assert not FeedImpression.objects.filter(viewer=mallory).exists()

    def test_retention_purges_old_rows(self, alice):
        post = Post.objects.create(author=alice, content='x')
        old = FeedImpression.objects.create(viewer=alice, post=post, position=0, ranker='v1',
                                            served_at=timezone.now() - timedelta(days=91))
        new = FeedImpression.objects.create(viewer=alice, post=post, position=0, ranker='v1',
                                            served_at=timezone.now() - timedelta(days=89))
        assert tasks.purge_old_impressions() == 1
        assert not FeedImpression.objects.filter(pk=old.pk).exists()
        assert FeedImpression.objects.filter(pk=new.pk).exists()

    def test_impressions_go_with_the_account(self, alice):
        post = Post.objects.create(author=make_user('x'), content='x')
        FeedImpression.objects.create(viewer=alice, post=post, position=0, ranker='v1', served_at=timezone.now())
        alice.delete()
        assert not FeedImpression.objects.exists()


# ── Events endpoint & privacy ────────────────────────────────────────────────

class TestEventsSecurity:
    url = '/api/ranking/events/'

    def _served(self, viewer, post, **kw):
        return FeedImpression.objects.create(viewer=viewer, post=post, position=0, ranker='v1',
                                             served_at=timezone.now() - timedelta(minutes=5), **kw)

    def test_dwell_and_open_update_own_impression(self, alice, bob):
        post = Post.objects.create(author=bob, content='x')
        imp = self._served(alice, post)
        r = client_for(alice).post(self.url, {'events': [
            {'post': post.id, 'dwell_ms': 1500}, {'post': post.id, 'dwell_ms': 10 ** 9, 'opened': True}]},
            format='json')
        assert r.status_code == 202 and r.data == {'accepted': 1}
        imp.refresh_from_db()
        assert imp.dwell_ms == impressions.MAX_DWELL_MS and imp.engaged and imp.engaged_at

    def test_cannot_report_on_posts_never_served(self, alice, bob):
        post = Post.objects.create(author=bob, content='x')
        r = client_for(alice).post(self.url, {'events': [{'post': post.id, 'opened': True}]}, format='json')
        assert r.status_code == 202 and r.data == {'accepted': 0}
        assert not FeedImpression.objects.exists()

    def test_cannot_touch_someone_elses_impression(self, alice, bob, mallory):
        post = Post.objects.create(author=bob, content='x')
        imp = self._served(alice, post)
        r = client_for(mallory).post(self.url, {'events': [{'post': post.id, 'dwell_ms': 999, 'opened': True}]},
                                     format='json')
        assert r.data == {'accepted': 0}
        imp.refresh_from_db()
        assert imp.dwell_ms is None and not imp.engaged

    def test_cannot_report_on_posts_no_longer_visible(self, alice, bob):
        friends_only = Post.objects.create(author=bob, content='x', privacy='friends')
        befriend(alice, bob)
        imp = self._served(alice, friends_only)
        Block.objects.create(blocker=bob, blocked=alice)
        r = client_for(alice).post(self.url, {'events': [{'post': friends_only.id, 'opened': True}]}, format='json')
        assert r.data == {'accepted': 0}
        imp.refresh_from_db()
        assert not imp.engaged

    def test_old_impressions_are_closed(self, alice, bob):
        post = Post.objects.create(author=bob, content='x')
        imp = FeedImpression.objects.create(viewer=alice, post=post, position=0, ranker='v1',
                                            served_at=timezone.now() - timedelta(hours=25))
        client_for(alice).post(self.url, {'events': [{'post': post.id, 'opened': True}]}, format='json')
        imp.refresh_from_db()
        assert not imp.engaged

    def test_batch_is_validated_and_capped(self, alice):
        c = client_for(alice)
        too_many = [{'post': i + 1} for i in range(impressions.MAX_PER_REQUEST + 1)]
        assert c.post(self.url, {'events': too_many}, format='json').status_code == 400
        assert c.post(self.url, {'events': []}, format='json').status_code == 400
        assert c.post(self.url, {'events': [{'post': 'x'}]}, format='json').status_code == 400
        assert c.post(self.url, {'events': [{'post': 1, 'dwell_ms': -5}]}, format='json').status_code == 400

    def test_anonymous_rejected_everywhere(self, db):
        c = APIClient()
        assert c.post(self.url, {'events': [{'post': 1}]}, format='json').status_code == 401
        assert c.get('/api/ranking/me/impressions/').status_code == 401
        assert c.get('/api/ranking/metrics/').status_code == 401

    def test_debug_view_shows_only_own_rows_and_redacts_social_features(self, alice, bob, mallory):
        post = Post.objects.create(author=bob, content='x')
        vec = [1.0] * len(features.FEATURES)
        self._served(alice, post, features=vec)
        self._served(mallory, post, features=vec)
        data = client_for(alice).get('/api/ranking/me/impressions/').data
        assert len(data['results']) == 1 and data['results'][0]['post'] == post.id
        f = data['results'][0]['features']
        assert f[F['mutual_friends']] is None and f[F['friend_engagements']] is None
        assert f[F['author_likes_30d']] == 1.0
        assert 'viewer' not in data['results'][0]

    def test_metrics_are_staff_only_and_aggregate(self, alice, bob):
        post = Post.objects.create(author=bob, content='x')
        self._served(alice, post, variant='v1')
        assert client_for(alice).get('/api/ranking/metrics/').status_code == 403
        staff = make_user('staff', is_staff=True)
        data = client_for(staff).get('/api/ranking/metrics/?days=evil').data
        assert data['days'] == 7
        assert data['arms'] == [{'variant': 'v1', 'ranker': 'v1', 'impressions': 1, 'engaged': 0,
                                 'engagement_rate': 0.0}]

    def test_feed_response_carries_no_impression_data(self, alice):
        Post.objects.create(author=alice, content='x')
        post = client_for(alice).get(feed_url()).data['results'][0]
        assert not {'features', 'impression', 'variant', 'probability'} & post.keys()


# ── Training ─────────────────────────────────────────────────────────────────

class TestTraining:
    def test_time_split_never_mixes_periods(self):
        base = timezone.now()
        t = sorted([base + timedelta(minutes=i // 3) for i in range(100)])
        tr, va, te = training.time_split(t)
        assert tr.stop == va.start and va.stop == te.start and te.stop == 100
        assert t[tr.stop - 1] < t[va.start] and t[va.stop - 1] < t[te.start]

    def test_trains_calibrates_and_beats_chance_quickly(self):
        import time

        import lightgbm  # noqa: F401  (time the training, not the first import)
        import sklearn.isotonic  # noqa: F401
        import sklearn.linear_model  # noqa: F401
        import sklearn.metrics  # noqa: F401
        X, y, t = synthetic_dataset()
        started = time.monotonic()
        booster, report = training.train(X, y, t, min_rows=100)
        assert time.monotonic() - started < 2
        m = report['metrics']['model']
        assert m['auc'] > 0.7 and m['ece'] < 0.1 and len(m['reliability']) == 10
        assert sum(r['n'] for r in m['reliability']) == m['n'] == report['rows']['test']
        assert report['calibration']['method'] in ('isotonic', 'platt')
        assert report['metrics']['baseline_v1']['auc'] is not None
        assert set(report['training_distribution']) == set(features.FEATURES)

    def test_refuses_too_little_data(self):
        X, y, t = synthetic_dataset(n=50)
        with pytest.raises(training.NotEnoughData):
            training.train(X, y, t)

    def test_psi(self):
        rng = np.random.default_rng(1)
        a = rng.normal(0, 1, 5000)
        edges = np.unique(np.quantile(a, np.linspace(0.1, 0.9, 9))).tolist()
        ref = training.distribution(a, edges)
        assert training.psi(ref, training.distribution(rng.normal(0, 1, 5000), edges)) < 0.05
        assert training.psi(ref, training.distribution(rng.normal(1, 1, 5000), edges)) > 0.2

    def test_train_ranker_command_end_to_end(self, alice, bob):
        X, y, t = synthetic_dataset(n=600)
        post = Post.objects.create(author=bob, content='x')
        shift = timezone.now() - timedelta(days=2) - t[-1]
        FeedImpression.objects.bulk_create([
            FeedImpression(viewer=alice, post=post, position=0, ranker='v1', variant='v1', synthetic=True,
                           served_at=ts + shift, engaged=bool(label), features=row.tolist())
            for row, label, ts in zip(X, y, t, strict=True)
        ])
        out = io.StringIO()
        with pytest.raises(CommandError):
            call_command('train_ranker', stdout=out)  # real data only by default: there is none
        call_command('train_ranker', '--synthetic', '--min-rows', '100', stdout=out)
        text = out.getvalue()
        assert 'SYNTHETIC DATA' in text and 'baseline v1 heuristic' in text and 'Reliability' in text
        model = model_store.current()
        assert model is not None and model.meta['synthetic'] is True
        assert model.meta['features'] == features.FEATURES
        assert model_store.latest_metadata_name().startswith('private/models/ranker-')


# ── Serving ──────────────────────────────────────────────────────────────────

class TestServing:
    def test_diversify_caps_runs_per_author(self):
        items = [('a', 1), ('a', 2), ('a', 3), ('a', 4), ('b', 5), ('c', 6)]
        out = serving.diversify(items, lambda x: x[0])
        authors = [a for a, _ in out]
        assert all(not (authors[i] == authors[i + 1] == authors[i + 2]) for i in range(len(authors) - 3))
        assert out[:3] == [('a', 1), ('a', 2), ('b', 5)]
        assert sorted(out) == sorted(items)

    def test_v2_serves_the_model_with_reasons(self, alice, bob, trained, settings,
                                              django_capture_on_commit_callbacks):
        settings.RANKING_FEED_RANKER_WEIGHTS = {'v1': 0, 'v2': 100}
        befriend(alice, bob)
        for i in range(4):
            Like.objects.create(user=alice, post=Post.objects.create(author=bob, content=f'old {i}'))
        others = [make_user(f'o{i}') for i in range(3)]
        for o in others:
            befriend(alice, o)
            for i in range(3):
                Post.objects.create(author=o, content=f'hello {i}')
        for i in range(4):
            Post.objects.create(author=bob, content=f'new {i}')
        # Everything about two days old, so recency doesn't dominate the explanations.
        Post.objects.update(created_at=timezone.now() - timedelta(hours=50))
        with django_capture_on_commit_callbacks(execute=True):
            data = client_for(alice).get(feed_url()).data['results']
        rows = list(FeedImpression.objects.filter(viewer=alice).order_by('position'))
        assert {r.ranker for r in rows} == {'v2'} and {r.variant for r in rows} == {'v2'}
        assert rows[0].model_version.startswith('ranker-') and all(r.features for r in rows)
        authors = [p['author']['id'] for p in data]
        assert all(not (authors[i] == authors[i + 1] == authors[i + 2]) for i in range(len(authors) - 2))
        assert all(p['reason'] for p in data)
        assert "Because you often like Thandi's posts" in {p['reason'] for p in data}

    def test_v2_feed_query_count_is_bounded(self, alice, trained, settings, django_assert_max_num_queries):
        settings.RANKING_FEED_RANKER_WEIGHTS = {'v1': 0, 'v2': 100}
        authors = [make_user(f'a{i}') for i in range(10)]
        for a in authors:
            befriend(alice, a)
        for i in range(60):
            Like.objects.create(user=alice, post=Post.objects.create(author=authors[i % 10], content=str(i)))
        c = client_for(alice)
        with django_assert_max_num_queries(50):
            r = c.get(feed_url())
        assert len(r.data['results']) == feed.PAGE_SIZE
        assert FeedImpression.objects.filter(ranker='v2').count() == feed.PAGE_SIZE

    def test_v2_without_a_model_falls_back_to_v1(self, alice, settings):
        settings.RANKING_FEED_RANKER_WEIGHTS = {'v1': 0, 'v2': 100}
        Post.objects.create(author=alice, content='x')
        data = client_for(alice).get(feed_url()).data['results']
        assert data[0]['reason'] == 'Your post'
        row = FeedImpression.objects.get(viewer=alice)
        assert row.variant == 'v2' and row.ranker == 'v1'

    def test_scoring_failure_falls_back_to_v1(self, alice, trained, settings, monkeypatch, caplog):
        settings.RANKING_FEED_RANKER_WEIGHTS = {'v1': 0, 'v2': 100}
        Post.objects.create(author=alice, content='x')

        def boom(*a, **kw):
            raise RuntimeError('bad model')
        monkeypatch.setattr(model_store.LoadedModel, 'predict', boom)
        r = client_for(alice).get(feed_url())
        assert r.status_code == 200 and len(r.data['results']) == 1
        assert FeedImpression.objects.get(viewer=alice).ranker == 'v1'
        assert 'Ranker v2 failed' in caplog.text

    def test_kill_switch(self, alice, settings):
        settings.RANKING_FEED_RANKER_WEIGHTS = {'v1': 0, 'v2': 100}
        assert serving.assigned_variant(alice) == 'v2'
        settings.RANKING_V2_ENABLED = False
        assert serving.assigned_variant(alice) == 'v1'

    def test_model_trained_on_other_features_is_ignored(self, trained, settings):
        name = model_store.latest_metadata_name()
        meta = model_store.read_metadata(name)
        meta['features'] = meta['features'][:-1]
        model_store.save('not a model', meta, '20990101T000000Z')
        model_store.reset()
        model_store._state['checked'] = 0
        assert model_store.current() is None

    def test_newer_model_is_picked_up(self, trained):
        first = model_store.current()
        X, y, t = synthetic_dataset(seed=9)
        booster, report = training.train(X, y, t, min_rows=100)
        meta = {'feature_version': features.FEATURE_VERSION, 'features': features.FEATURES, **report}
        model_store.save(booster.model_to_string(), meta, '20300101T000000Z')
        assert model_store.current().name != first.name == 'ranker-20260101T000000Z'

    def test_reasons_are_true_and_safe(self, alice, bob):
        post = Post.objects.create(author=bob, content='x')
        f = [0.0] * len(features.FEATURES)
        f[F['author_likes_30d']] = math.log1p(1)  # one like is not "often"
        f[F['mutual_friends']] = math.log1p(5)
        f[F['friend_engagements']] = math.log1p(1)  # one friend's like is not "popular with your friends"
        now = timezone.now()
        drivers = ['mutual_friends', 'author_likes_30d', 'friend_engagements', 'interest_similarity']
        assert serving.reason(post, f, drivers, now) == 'Recent post'
        f[F['author_likes_30d']] = math.log1p(4)
        assert serving.reason(post, f, drivers, now) == "Because you often like Thandi's posts"
        f[F['interest_similarity']] = 0.8
        assert serving.reason(post, f, ['interest_similarity'], now) == "Similar to posts you've engaged with"
        f[F['friend_engagements']] = math.log1p(3)
        assert serving.reason(post, f, ['friend_engagements'], now) == 'Popular with your friends'


# ── Drift ────────────────────────────────────────────────────────────────────

class TestDrift:
    def test_psi_task_feeds_the_gauge(self, alice, trained):
        from prometheus_client import REGISTRY, generate_latest

        post = Post.objects.create(author=alice, content='x')
        vec = [0.0] * len(features.FEATURES)
        vec[F['age_hours']] = 9.0  # far older than anything in training
        FeedImpression.objects.bulk_create([
            FeedImpression(viewer=alice, post=post, position=0, ranker='v2', served_at=timezone.now(),
                           features=vec, synthetic=True) for _ in range(50)])
        result = tasks.compute_feature_psi()
        assert result['age_hours'] > 0.2
        text = generate_latest(REGISTRY).decode()
        assert 'ranking_feature_psi{feature="age_hours"}' in text

    def test_serving_exports_feature_means(self, alice, trained, settings):
        from prometheus_client import REGISTRY
        settings.RANKING_FEED_RANKER_WEIGHTS = {'v1': 0, 'v2': 100}
        Post.objects.create(author=alice, content='x')
        client_for(alice).get(feed_url())
        assert REGISTRY.get_sample_value('ranking_feature_mean', {'feature': 'is_own_post'}) == 1.0


# ── A/B readout & simulation ─────────────────────────────────────────────────

class TestExperimentTools:
    def test_two_proportion(self):
        t = two_proportion(100, 1000, 130, 1000)
        assert t['diff'] == pytest.approx(0.03)
        assert t['z'] == pytest.approx(2.1027, abs=1e-3)
        assert t['p_value'] == pytest.approx(0.0355, abs=1e-3)
        assert t['ci'][0] < 0.03 < t['ci'][1]

    def test_ab_report(self, alice, bob):
        post = Post.objects.create(author=bob, content='x')
        now = timezone.now()
        rows = []
        for viewer, variant, rate in ((alice, 'v1', 0.1), (bob, 'v2', 0.2)):
            for i in range(200):
                rows.append(FeedImpression(viewer=viewer, post=post, position=0, variant=variant, ranker=variant,
                                           served_at=now - timedelta(hours=i % 48), engaged=i < 200 * rate))
        FeedImpression.objects.bulk_create(rows)
        HiddenPost.objects.create(user=alice, post=post)
        out = io.StringIO()
        call_command('ab_report', 'feed_ranker', stdout=out)
        text = out.getvalue()
        assert 'v2 - v1: +10.00%' in text and 'p = ' in text and '95% CI' in text
        with pytest.raises(CommandError):
            call_command('ab_report', 'nope', stdout=out)

    def test_simulation_is_dev_only_and_seed_only(self, settings, db):
        settings.DEBUG = False
        with pytest.raises(CommandError):
            call_command('simulate_feed_engagement', '--days', '1', stdout=io.StringIO())
        real = make_user('real')  # @example.com: never touched
        seeds = [get_seed(i) for i in range(4)]
        for a in seeds:
            for b in seeds:
                if a.id < b.id:
                    befriend(a, b)
            for i in range(4):
                Post.objects.create(author=a, content=f'{a.username} {i}')
        befriend(real, seeds[0])
        Post.objects.create(author=real, content='real person')
        out = io.StringIO()
        call_command('simulate_feed_engagement', '--days', '2', '--sessions', '2', '--i-know-this-is-not-production',
                     stdout=out)
        assert 'SYNTHETIC DATA' in out.getvalue()
        assert FeedImpression.objects.exists()
        assert not FeedImpression.objects.filter(synthetic=False).exists()
        assert not FeedImpression.objects.filter(viewer=real).exists()
        assert not FeedImpression.objects.filter(post__author=real).exists()


def get_seed(i):
    from django.contrib.auth import get_user_model
    return get_user_model().objects.create_user(username=f'demo{i}', email=f'demo{i}@example.test',
                                                password='andromeda-demo-pass')
