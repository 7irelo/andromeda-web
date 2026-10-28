"""
Semantic search and Ask Andromeda.

The leak tests are the important ones: whatever the ranking does, content the
viewer can't open must never be returned, and must never be sent to the
answer model.
"""
import hashlib
import math
import re

import pytest
from django.db import connection
from django.test import override_settings

from core import ai_client
from core.test_security import befriend, client_for, make_user
from groups.models import Group, GroupMember
from marketplace.models import Listing
from posts.models import Post
from users.models import Block

from . import documents, hybrid, tasks
from .models import DIMS, Embedding

postgres_only = pytest.mark.skipif(connection.vendor != 'postgresql', reason='needs pgvector')


def fake_vector(text):
    """Deterministic hashed bag-of-words embedding: similar words, similar vectors."""
    v = [0.0] * DIMS
    for word in re.findall(r'\w+', text.lower()):
        v[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIMS] += 1.0  # noqa: S324 - not security
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


class FakeAI:
    def __init__(self, answer=None):
        self.calls = []
        self.answer = answer

    def __call__(self, path, payload, user_id):
        self.calls.append((path, payload, user_id))
        if path == '/v1/embed':
            return {'vectors': [fake_vector(t) for t in payload['texts']], 'model': 'fake', 'dims': DIMS}
        if path == '/v1/search/plan':
            return {'plan': {'query': payload['q'], 'types': []}, 'vector': fake_vector(payload['q']),
                    'rewritten': False}
        if path == '/v1/ask':
            ids = [s['id'] for s in payload['sources']]
            return self.answer or {'answer': {'abstain': not ids, 'answer': 'From your feed.',
                                              'claims': [{'text': 'x', 'source_ids': ids[:2]}]}}
        raise AssertionError(path)


@pytest.fixture(autouse=True)
def _fresh_cache():
    from django.core.cache import cache
    cache.clear()


@pytest.fixture
def ai(monkeypatch):
    fake = FakeAI()
    monkeypatch.setattr(ai_client, 'enabled', lambda: True)
    monkeypatch.setattr(ai_client, 'call', fake)
    return fake


@pytest.fixture
def people(db):
    return make_user('alice'), make_user('bob'), make_user('mallory')


def _post(author, content, **kw):
    return Post.objects.create(author=author, content=content, **kw)


# ── Documents & indexing ─────────────────────────────────────────────────────

def test_chunking_respects_paragraphs_and_caps():
    text = '\n'.join(['para ' * 100] * 30)
    pieces = documents._chunks(text)
    assert 1 < len(pieces) <= documents.MAX_CHUNKS
    assert all(len(p) <= documents.CHUNK_CHARS for p in pieces)


def test_post_document_includes_top_comments_but_not_removed_ones(people):
    from posts.models import Comment
    alice, bob, _ = people
    p = _post(alice, 'Parkrun at Delta Park')
    Comment.objects.create(post=p, author=bob, content='See you there')
    Comment.objects.create(post=p, author=bob, content='spam spam', moderation_status='removed')
    doc = documents.load('posts', p.id)
    assert 'See you there' in doc.text and 'spam spam' not in doc.text


def test_removed_content_is_not_indexed(people):
    alice = people[0]
    p = _post(alice, 'hello', moderation_status='removed')
    assert documents.load('posts', p.id) is None


@pytest.mark.django_db(transaction=True)
def test_index_is_idempotent_and_follows_edits_and_deletes(ai):
    alice = make_user('alice')
    with override_settings(AI_SEARCH_ENABLED=True):
        p = _post(alice, 'Braai at the park on Saturday')
        assert Embedding.objects.filter(kind='posts', object_id=p.id).count() == 1
        embeds = sum(1 for c in ai.calls if c[0] == '/v1/embed')
        assert tasks.index_object('posts', p.id) == 'unchanged'
        assert sum(1 for c in ai.calls if c[0] == '/v1/embed') == embeds
        p.content = 'Braai moved to Sunday'
        p.save()
        assert 'Sunday' in Embedding.objects.get(kind='posts', object_id=p.id).text
        pid = p.id
        p.delete()
        assert not Embedding.objects.filter(kind='posts', object_id=pid).exists()
    # Indexing runs under the system identity, never an end user's budget.
    assert {c[2] for c in ai.calls if c[0] == '/v1/embed'} == {tasks.SYSTEM_USER}


# ── Leak tests ───────────────────────────────────────────────────────────────

def _private_world(alice, bob, mallory):
    """Bob's content in every visibility state, all mentioning 'zebra'."""
    befriend(alice, bob)
    secret = Group.objects.create(name='Zebra secret club', privacy=Group.PRIVACY_SECRET, created_by=bob)
    GroupMember.objects.create(group=secret, user=bob, role=GroupMember.ROLE_ADMIN)
    return {
        'public': _post(bob, 'zebra public post'),
        'friends': _post(bob, 'zebra friends only post', privacy=Post.PRIVACY_FRIENDS),
        'only_me': _post(bob, 'zebra only me post', privacy=Post.PRIVACY_PRIVATE),
        'removed': _post(bob, 'zebra removed post', moderation_status='removed'),
        'group': _post(bob, 'zebra secret group post', group=secret),
        'secret_group': secret,
    }


def _seen_post_ids(client):
    r = client.get('/api/search/semantic/', {'q': 'zebra'})
    assert r.status_code == 200, r.content
    return {x['item']['id'] for x in r.json()['results'] if x['type'] == 'posts'}


def test_semantic_search_never_returns_invisible_content(people):
    alice, bob, mallory = people
    w = _private_world(alice, bob, mallory)
    assert _seen_post_ids(client_for(mallory)) == {w['public'].id}
    assert _seen_post_ids(client_for(alice)) == {w['public'].id, w['friends'].id}
    assert w['only_me'].id in _seen_post_ids(client_for(bob))


def test_blocking_hides_search_results_both_ways(people):
    alice, bob, _ = people
    _post(bob, 'zebra public post')
    Block.objects.create(blocker=alice, blocked=bob)
    assert _seen_post_ids(client_for(alice)) == set()


def test_ask_never_sends_invisible_content_to_the_model(people, ai):
    alice, bob, mallory = people
    w = _private_world(alice, bob, mallory)
    r = client_for(mallory).post('/api/ask/', {'question': 'zebra'}, format='json')
    assert r.status_code == 200, r.content
    ask = [c for c in ai.calls if c[0] == '/v1/ask'][0]
    sent = {s['id'] for s in ask[1]['sources']}
    assert sent <= {f"posts:{w['public'].id}"}
    assert all('friends only' not in s['text'] and 'only me' not in s['text'] and 'secret' not in s['text']
               for s in ask[1]['sources'])
    assert ask[2] == mallory.id  # billed to, and acting as, the asker


def test_ask_maps_citations_to_links_and_drops_unknown_ids(people, ai):
    alice = people[0]
    p = _post(alice, 'Delta Park parkrun every Saturday at 8')
    ai.answer = {'answer': {'abstain': False, 'answer': 'Saturdays at 8.',
                            'claims': [{'text': 'parkrun', 'source_ids': [f'posts:{p.id}', 'posts:999999']}]}}
    r = client_for(alice).post('/api/ask/', {'question': 'parkrun'}, format='json')
    body = r.json()
    assert body['claims'][0]['sources'] == [{'type': 'posts', 'id': p.id, 'title': p.content[:120],
                                             'author': 'alice', 'url': f'/posts/{p.id}'}]


def test_ask_unavailable_without_ai_service(people):
    r = client_for(people[0]).post('/api/ask/', {'question': 'anything?'}, format='json')
    assert r.status_code == 503


def test_search_degrades_to_lexical_when_ai_is_down(people, monkeypatch):
    alice, bob, _ = people
    _post(bob, 'zebra public post')
    monkeypatch.setattr(ai_client, 'enabled', lambda: True)

    def down(*a, **k):
        raise ai_client.AIUnavailable('down')
    monkeypatch.setattr(ai_client, 'call', down)
    r = client_for(alice).get('/api/search/semantic/', {'q': 'zebra'})
    assert r.status_code == 200 and r.json()['semantic'] is False and len(r.json()['results']) == 1


def test_listing_results_exclude_sold_and_removed(people):
    alice, bob, _ = people
    Listing.objects.create(seller=bob, title='Zebra print couch', description='3-seater', price=100)
    Listing.objects.create(seller=bob, title='Zebra lamp', description='sold', price=10, status=Listing.STATUS_SOLD)
    Listing.objects.create(seller=bob, title='Zebra scam', description='x', price=1, moderation_status='removed')
    r = client_for(alice).get('/api/search/semantic/', {'q': 'zebra', 'type': 'listings'})
    assert [x['item']['title'] for x in r.json()['results']] == ['Zebra print couch']


def test_rrf_prefers_items_both_retrievers_agree_on():
    fused = dict(hybrid.rrf(['a', 'b', 'c'], ['c', 'a', 'd']))
    assert max(fused, key=fused.get) == 'a' and fused['c'] > fused['b']


# ── Dense retrieval (Postgres + pgvector only) ──────────────────────────────

@postgres_only
@pytest.mark.django_db(transaction=True)
def test_dense_retrieval_respects_visibility(ai):
    alice, bob, mallory = make_user('alice'), make_user('bob'), make_user('mallory')
    with override_settings(AI_SEARCH_ENABLED=True):
        w = _private_world(alice, bob, mallory)
        for p in Post.objects.all():
            tasks.index_object('posts', p.id)
        plan = hybrid.Plan(query='zebra', vector=fake_vector('zebra post'))
        _, hits = hybrid.search(mallory, 'nothing lexical', ['posts'], mode='dense', plan=plan)
    assert {h.id for h in hits} == {w['public'].id}
