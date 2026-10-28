from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

import outbox
from outbox import drain, metrics, reconcile
from outbox.graph import InMemoryGraph
from outbox.models import GraphDrift, OutboxEvent
from posts.models import Like, Post
from users import graph_sync
from users.models import FriendRequest

User = get_user_model()


@pytest.fixture
def neo4j_on(settings):
    settings.NEO4J_ENABLED = True
    return settings


def _user(name):
    return User.objects.create_user(username=name, password='pass-1234567', email=f'{name}@example.com')


def _kinds():
    return list(OutboxEvent.objects.values_list('kind', flat=True))


class TestEmit:
    def test_changes_record_events(self, db):
        a, b = _user('ana'), _user('ben')
        FriendRequest.objects.create(sender=a, receiver=b, status=FriendRequest.STATUS_ACCEPTED)
        post = Post.objects.create(author=a, content='hi')
        Like.objects.create(user=b, post=post)
        assert _kinds() == ['graph.sync_user', 'graph.sync_user', 'graph.link_friends',
                            'graph.sync_post', 'graph.link_like']
        assert OutboxEvent.objects.get(kind='graph.link_like').payload == {'user_id': b.id, 'post_id': post.id}

    def test_events_are_recorded_even_with_neo4j_off(self, db, settings):
        settings.NEO4J_ENABLED = False
        _user('ana')
        assert _kinds() == ['graph.sync_user']

    def test_unknown_kind_is_refused(self, db):
        with pytest.raises(ValueError):
            outbox.emit('graph.drop_everything')

    def test_legacy_enqueue_shim_records_named_payload(self, db):
        graph_sync.enqueue(graph_sync.link_friends, 4, 5)
        assert OutboxEvent.objects.get().payload == {'a_id': 4, 'b_id': 5}

    def test_irrelevant_user_saves_record_nothing(self, db):
        user = _user('ana')
        OutboxEvent.objects.all().delete()
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])
        assert not OutboxEvent.objects.exists()


@pytest.mark.django_db(transaction=True)
class TestAtomicity:
    def test_rolled_back_change_leaves_no_event(self):
        author = _user('ana')
        before = OutboxEvent.objects.count()
        with pytest.raises(RuntimeError):
            with transaction.atomic():
                Post.objects.create(author=author, content='never happened')
                assert OutboxEvent.objects.filter(kind='graph.sync_post').exists()
                raise RuntimeError
        assert not Post.objects.filter(content='never happened').exists()
        assert OutboxEvent.objects.count() == before
        assert not OutboxEvent.objects.filter(kind='graph.sync_post').exists()

    def test_committed_change_keeps_its_event(self):
        author = _user('ana')
        with transaction.atomic():
            post = Post.objects.create(author=author, content='kept')
        assert OutboxEvent.objects.filter(kind='graph.sync_post', payload__post_id=post.id).exists()


class TestDrain:
    def test_applies_events_in_order(self, db, neo4j_on):
        a, b = _user('ana'), _user('ben')
        FriendRequest.objects.create(sender=a, receiver=b, status=FriendRequest.STATUS_ACCEPTED)
        post = Post.objects.create(author=a, content='hi')
        Like.objects.create(user=b, post=post)
        graph = InMemoryGraph()

        stats = drain.drain(graph=graph)

        assert stats == {'processed': 5, 'failed': 0, 'dead': 0}
        assert set(graph.users) == {a.id, b.id}
        assert graph.friends == {frozenset((a.id, b.id))}
        assert graph.likes == {(b.id, post.id)}
        assert not OutboxEvent.objects.pending().exists()

    def test_drain_is_idempotent(self, db, neo4j_on):
        a, b = _user('ana'), _user('ben')
        FriendRequest.objects.create(sender=a, receiver=b, status=FriendRequest.STATUS_ACCEPTED)
        post = Post.objects.create(author=a, content='hi')
        Like.objects.create(user=b, post=post)
        graph = InMemoryGraph()
        drain.drain(graph=graph)
        snapshot = (dict(graph.users), set(graph.friends), dict(graph.posts), set(graph.likes))

        # A second tick has nothing to do...
        assert drain.drain(graph=graph) == {'processed': 0, 'failed': 0, 'dead': 0}
        # ...and re-applying every event (as after a crash before commit) changes nothing.
        OutboxEvent.objects.update(processed_at=None)
        assert drain.drain(graph=graph)['processed'] == 5
        assert (dict(graph.users), set(graph.friends), dict(graph.posts), set(graph.likes)) == snapshot

    def test_delete_after_create_converges(self, db, neo4j_on):
        a = _user('ana')
        post = Post.objects.create(author=a, content='hi')
        post.delete()
        graph = InMemoryGraph()
        drain.drain(graph=graph)
        assert graph.posts == {}

    def test_neo4j_off_marks_events_processed(self, db, settings):
        settings.NEO4J_ENABLED = False
        _user('ana')
        assert drain.drain() == {'processed': 1, 'failed': 0, 'dead': 0}
        assert OutboxEvent.objects.get().processed_at is not None

    def test_unknown_kind_is_dead_lettered(self, db, neo4j_on):
        OutboxEvent.objects.create(kind='graph.nope', payload={})
        assert drain.drain(graph=InMemoryGraph())['dead'] == 1
        assert OutboxEvent.objects.get().dead_at is not None


class FlakyGraph(InMemoryGraph):
    def __init__(self, exc):
        super().__init__()
        self.exc = exc

    def upsert_users(self, users):
        raise self.exc


class TestRetries:
    def test_failure_backs_off_with_jitter(self, db, neo4j_on):
        _user('ana')
        now = timezone.now()
        stats = drain.drain(graph=FlakyGraph(ValueError('boom')), now=now)
        event = OutboxEvent.objects.get()
        assert stats['failed'] == 1
        assert event.attempts == 1 and event.processed_at is None and event.dead_at is None
        assert event.last_error == 'ValueError: boom'
        # First retry: base 5 s with equal jitter -> between 2.5 and 5 s.
        assert now + timedelta(seconds=2.5) <= event.next_attempt_at <= now + timedelta(seconds=5)
        # Not due yet: the next tick leaves it alone.
        assert drain.drain(graph=InMemoryGraph(), now=now + timedelta(seconds=1))['processed'] == 0
        assert drain.drain(graph=InMemoryGraph(), now=now + timedelta(seconds=6))['processed'] == 1

    def test_backoff_grows_and_is_capped(self, settings):
        settings.OUTBOX_BACKOFF_BASE_SECONDS = 5
        settings.OUTBOX_BACKOFF_MAX_SECONDS = 60
        for attempts, (lo, hi) in {1: (2.5, 5), 2: (5, 10), 3: (10, 20), 10: (30, 60)}.items():
            for _ in range(20):
                assert lo <= drain.backoff_seconds(attempts) <= hi

    def test_dead_letters_after_max_attempts(self, db, neo4j_on):
        neo4j_on.OUTBOX_MAX_ATTEMPTS = 3
        _user('ana')
        graph = FlakyGraph(ValueError('boom'))
        now = timezone.now()
        for _ in range(3):
            now += timedelta(hours=2)
            drain.drain(graph=graph, now=now)
        event = OutboxEvent.objects.get()
        assert event.attempts == 3 and event.dead_at is not None
        assert drain.drain(graph=InMemoryGraph(), now=now + timedelta(days=1))['processed'] == 0

        assert drain.requeue_dead() == 1
        assert drain.drain(graph=InMemoryGraph())['processed'] == 1

    def test_connection_error_stops_the_batch(self, db, neo4j_on):
        _user('ana')
        _user('ben')
        stats = drain.drain(graph=FlakyGraph(ConnectionError('neo4j down')))
        assert stats == {'processed': 0, 'failed': 1, 'dead': 0}
        assert list(OutboxEvent.objects.order_by('id').values_list('attempts', flat=True)) == [1, 0]

    def test_purge_keeps_recent_and_unprocessed(self, db):
        old = OutboxEvent.objects.create(kind='graph.delete_user', payload={'user_id': 1},
                                         processed_at=timezone.now() - timedelta(days=30))
        recent = OutboxEvent.objects.create(kind='graph.delete_user', payload={'user_id': 2},
                                            processed_at=timezone.now())
        pending = OutboxEvent.objects.create(kind='graph.delete_user', payload={'user_id': 3})
        assert drain.purge_processed() == 1
        assert set(OutboxEvent.objects.values_list('id', flat=True)) == {recent.id, pending.id}
        assert not OutboxEvent.objects.filter(id=old.id).exists()


class TestReconcile:
    def _world(self):
        a, b, c = _user('ana'), _user('ben'), _user('cy')
        FriendRequest.objects.create(sender=a, receiver=b, status=FriendRequest.STATUS_ACCEPTED)
        FriendRequest.objects.create(sender=c, receiver=a, status=FriendRequest.STATUS_ACCEPTED)
        FriendRequest.objects.create(sender=b, receiver=c)  # pending: not an edge
        p1 = Post.objects.create(author=a, content='one')
        p2 = Post.objects.create(author=b, content='two')
        Like.objects.create(user=b, post=p1)
        Like.objects.create(user=c, post=p2)
        return a, b, c, p1, p2

    def test_repairs_drift_in_batches(self, db):
        a, b, c, p1, p2 = self._world()
        graph = InMemoryGraph()
        graph.upsert_users([{'user_id': a.id, 'username': 'ana', 'display_name': 'ana', 'is_verified': False},
                            {'user_id': 9999, 'username': 'ghost', 'display_name': 'ghost', 'is_verified': False}])
        graph.upsert_posts([{'post_id': p1.id, 'author_id': a.id}, {'post_id': 8888, 'author_id': a.id}])
        graph.friends.add(frozenset((a.id, 9999)))

        result = reconcile.reconcile(graph=graph, batch=2)

        # users: b, c missing + ghost extra; friendships: 2 missing (+ ghost edge went with its node);
        # posts: p2 missing + 8888 extra; likes: 2 missing.
        assert result == {'user': 3, 'friendship': 2, 'post': 2, 'like': 2}
        assert set(graph.users) == {a.id, b.id, c.id}
        assert graph.friends == {frozenset((a.id, b.id)), frozenset((a.id, c.id))}
        assert set(graph.posts) == {p1.id, p2.id}
        assert graph.likes == {(b.id, p1.id), (c.id, p2.id)}

        assert reconcile.reconcile(graph=graph, batch=2) == {'user': 0, 'friendship': 0, 'post': 0, 'like': 0}
        drift = {d.kind: (d.total, d.last_run) for d in GraphDrift.objects.all()}
        assert drift == {'user': (3, 0), 'friendship': (2, 0), 'post': (2, 0), 'like': (2, 0)}

    def test_dry_run_reports_without_repairing(self, db):
        self._world()
        graph = InMemoryGraph()
        result = reconcile.reconcile(graph=graph, repair=False)
        assert result['user'] == 3 and graph.users == {}

    def test_drained_outbox_leaves_no_drift(self, db, neo4j_on):
        self._world()
        graph = InMemoryGraph()
        drain.drain(graph=graph)
        assert sum(reconcile.reconcile(graph=graph).values()) == 0


class TestMetrics:
    def test_collector_reports_lag_dead_letters_and_drift(self, db):
        OutboxEvent.objects.create(kind='graph.delete_user', payload={'user_id': 1},
                                   created_at=timezone.now() - timedelta(minutes=5))
        OutboxEvent.objects.create(kind='graph.delete_user', payload={'user_id': 2}, dead_at=timezone.now())
        GraphDrift.objects.create(kind='like', total=7, last_run=2, checked_at=timezone.now())

        samples = {(s.name, tuple(sorted(s.labels.items()))): s.value
                   for family in metrics.OutboxCollector().collect() for s in family.samples}

        assert samples[('outbox_pending_events', ())] == 1
        assert samples[('outbox_dead_letter_events', ())] == 1
        assert samples[('outbox_oldest_pending_age_seconds', ())] >= 299
        assert samples[('graph_drift_total', (('kind', 'like'),))] == 7
        assert samples[('graph_drift_last_run', (('kind', 'like'),))] == 2

    def test_describe_needs_no_database(self):
        names = {f.name for f in metrics.OutboxCollector().describe()}
        assert 'graph_drift' in names and 'outbox_pending_events' in names
