"""The search-rewrite cache: exact and semantic hits, eviction, and what is never stored."""
import asyncio

from app.features.query_cache import QueryCache, normalise, shorten
from app.features.retrieval import QueryPlan, QueryRequest, plan_query


def unit(*head):
    return list(head) + [0.0] * (1536 - len(head))


def test_normalise_ignores_case_and_spacing():
    assert normalise('  Couch   IN Durban ') == 'couch in durban'


def test_shorten_gives_a_unit_vector():
    v = shorten(unit(3.0, 4.0))
    assert len(v) == 256 and abs(v[0] - 0.6) < 1e-9 and abs(v[1] - 0.8) < 1e-9


def test_exact_and_semantic_hits_and_misses():
    cache = QueryCache(threshold=0.95)
    cache.put('couch', unit(1.0, 0.0), 'plan')
    assert cache.get('COUCH', unit(0.0, 1.0)) == ('plan', 'exact')
    assert cache.get('sofa', unit(1.0, 0.1)) == ('plan', 'semantic')
    assert cache.get('fridge', unit(0.0, 1.0)) is None


def test_oldest_entry_is_evicted():
    cache = QueryCache(max_entries=2)
    cache.put('a', unit(1.0), 1)
    cache.put('b', unit(0.0, 1.0), 2)
    cache.get('a', unit(1.0))
    cache.put('c', unit(0.0, 0.0, 1.0), 3)
    assert len(cache) == 2 and cache.get('b', unit(0.0, 1.0)) is None


class FakeGateway:
    def __init__(self, plan):
        self.plan = plan
        self.rewrites = 0

    async def embed(self, job, *, texts, user_id):
        return type('E', (), {'vectors': [unit(1.0, 0.0) for _ in texts]})()

    async def structured(self, job, *, system, user, schema, user_id):
        self.rewrites += 1
        return type('R', (), {'output': self.plan.model_copy()})()


def run(gateway, cache, q='couch durban'):
    return asyncio.run(plan_query(QueryRequest(q=q), gateway, 1, cache))


def test_second_similar_query_skips_the_rewrite():
    gateway, cache = FakeGateway(QueryPlan(query='couch Durban', types=['listings'])), QueryCache()
    first = run(gateway, cache)
    second = run(gateway, cache, 'couches durban')
    assert gateway.rewrites == 1 and second.plan == first.plan and second.vector == first.vector and second.rewritten


def test_plans_naming_a_person_are_never_stored():
    gateway, cache = FakeGateway(QueryPlan(query='braai', types=[], author='Thandi')), QueryCache()
    run(gateway, cache)
    run(gateway, cache)
    assert gateway.rewrites == 2 and len(cache) == 0


def test_no_cache_keeps_the_old_path():
    gateway = FakeGateway(QueryPlan(query='couch', types=[]))
    assert run(gateway, None).rewritten and gateway.rewrites == 1
