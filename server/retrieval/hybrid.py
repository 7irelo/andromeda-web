"""
Hybrid search: lexical (Postgres full-text) and dense (pgvector cosine)
retrieval fused with Reciprocal Rank Fusion, optionally reranked.

Privacy is enforced inside the SQL. Both retrievers start from the viewer's
visibility-filtered queryset (the same one the feature endpoints use), so
content the viewer can't open never becomes a candidate. Filtering after
retrieval would leak through counts and timing, and would hurt recall.
"""
import datetime as dt
import hashlib
import logging
from dataclasses import dataclass, field

from django.conf import settings
from django.core.cache import cache
from django.db import connection, transaction
from django.utils import timezone

from core import ai_client
from core.search import CONTENT, lexical

from .models import Embedding

logger = logging.getLogger(__name__)

CANDIDATES = 50   # per retriever, per content type
RRF_K = 60
RERANK_TOP = 20
PLAN_CACHE_SECONDS = 3600
MODES = ('lexical', 'dense', 'hybrid')


@dataclass
class Plan:
    query: str
    types: list[str] = field(default_factory=list)
    since_days: int | None = None
    author: str | None = None
    vector: list[float] | None = None
    rewritten: bool = False


@dataclass
class Hit:
    kind: str
    id: int
    score: float
    sources: list[str]


def plan_query(q, user_id, rewrite=None, opted_out=False):
    """Ask the AI service for a query plan and embedding. Falls back to lexical-only on any failure."""
    if rewrite is None:
        rewrite = settings.AI_SEARCH_REWRITE
    if opted_out or not (settings.AI_SEARCH_ENABLED and ai_client.enabled()):
        return Plan(query=q)
    # Plans depend only on the query text, never on the viewer, so they're safe to share.
    key = 'search-plan:' + hashlib.sha256(f'{int(rewrite)}:{q}'.encode()).hexdigest()
    data = cache.get(key)
    if data is None:
        try:
            data = ai_client.call('/v1/search/plan', {'q': q, 'rewrite': rewrite}, user_id=user_id)
        except (ai_client.AIUnavailable, ai_client.AIRejected) as exc:
            logger.info('Search plan unavailable, using lexical search: %s', exc)
            return Plan(query=q)
        cache.set(key, data, PLAN_CACHE_SECONDS)
    p = data['plan']
    return Plan(query=p['query'], types=p.get('types') or [], since_days=p.get('since_days'),
                author=p.get('author'), vector=data['vector'], rewritten=data.get('rewritten', False))


def _scoped(kind, user, plan):
    qs = CONTENT[kind][0](user)
    if plan.since_days:
        qs = qs.filter(created_at__gte=timezone.now() - dt.timedelta(days=plan.since_days))
    if plan.author:
        author_field = {'posts': 'author__username', 'listings': 'seller__username',
                        'videos': 'uploader__username'}.get(kind)
        if author_field:
            narrowed = qs.filter(**{f'{author_field}__iexact': plan.author})
            if narrowed.exists():  # an author the rewriter misread shouldn't empty the results
                qs = narrowed
    return qs


def _lexical_ids(kind, user, q, scoped):
    qs = lexical(kind, user, q).filter(pk__in=scoped.values('pk'))
    return list(dict.fromkeys(qs.values_list('pk', flat=True)[:CANDIDATES]))


def _dense_ids(kind, scoped, vector):
    if vector is None or connection.vendor != 'postgresql':
        return []
    from pgvector.django import CosineDistance
    with transaction.atomic():
        with connection.cursor() as cur:
            # With a filter on the HNSW scan, keep scanning until enough rows pass it.
            cur.execute("SET LOCAL hnsw.iterative_scan = 'relaxed_order'")
        rows = (Embedding.objects.filter(kind=kind, object_id__in=scoped.values('pk'))
                .annotate(d=CosineDistance('vector', vector)).order_by('d')
                .values_list('object_id', flat=True)[:CANDIDATES * 3])
        return list(dict.fromkeys(rows))[:CANDIDATES]


def rrf(*rankings):
    scores = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking):
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank + 1)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


def _rerank(q, hits, user_id):
    from . import documents
    top = hits[:RERANK_TOP]
    candidates = []
    for h in top:
        doc = documents.load(h.kind, h.id)
        if doc:
            candidates.append({'id': f'{h.kind}:{h.id}', 'text': doc.text[:1500]})
    if not candidates:
        return hits
    try:
        res = ai_client.call('/v1/search/rerank', {'query': q, 'candidates': candidates}, user_id=user_id)
    except (ai_client.AIUnavailable, ai_client.AIRejected):
        return hits
    by_key = {f'{h.kind}:{h.id}': h for h in top}
    ordered = [by_key[i] for i in res['ids'] if i in by_key]
    # Keep anything the reranker judged irrelevant only after the ones it kept.
    rest = [h for h in top if h not in ordered]
    return ordered + rest + hits[RERANK_TOP:]


def search(user, q, kinds, *, mode='hybrid', plan=None, rerank=None, limit=20):
    """Ranked hits across content types, all drawn from what `user` may see."""
    if plan is None:
        opted_out = getattr(user, 'ai_opt_out', False)
        plan = Plan(query=q) if mode == 'lexical' else plan_query(q, user.id, opted_out=opted_out)
    if plan.types:
        narrowed = [k for k in kinds if k in plan.types]
        kinds = narrowed or kinds
    rankings = []
    for kind in kinds:
        scoped = _scoped(kind, user, plan)
        lex, dense = [], []
        if mode in ('lexical', 'hybrid'):
            # Match the user's words and the rewrite: rewrites add synonyms but can drop rare terms.
            lex = _lexical_ids(kind, user, q, scoped)
            if plan.rewritten and plan.query.lower() != q.lower():
                lex = [i for i, _ in rrf(lex, _lexical_ids(kind, user, plan.query, scoped))]
        if mode in ('dense', 'hybrid'):
            dense = _dense_ids(kind, scoped, plan.vector)
        rankings.append(([(kind, i) for i in lex], [(kind, i) for i in dense]))

    fused = rrf(*[r for pair in rankings for r in pair if r])
    lex_keys = {k for pair in rankings for k in pair[0]}
    dense_keys = {k for pair in rankings for k in pair[1]}
    hits = [Hit(kind, oid, round(score, 5),
                [s for s, keys in (('lexical', lex_keys), ('semantic', dense_keys)) if (kind, oid) in keys])
            for (kind, oid), score in fused]
    if rerank is None:
        rerank = settings.AI_SEARCH_RERANK
    if rerank and plan.vector is not None and len(hits) > 1:
        hits = _rerank(q, hits, user.id)
    return plan, hits[:limit]
