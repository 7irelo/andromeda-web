"""
Semantic search and "Ask Andromeda".

The AI service never sees the database. Django decides what the viewer may
see, retrieves only from that set, and sends the candidates here. This module:

- embeds documents and queries;
- rewrites a search query into a plan (cleaner query text, content types,
  time window) with structured output;
- reranks a short candidate list (listwise, ids verified);
- writes grounded answers whose every claim must cite source ids that were
  actually provided. Unsupported claims are dropped, and the model is told to
  abstain when the sources don't answer the question.
"""
from typing import Literal

from pydantic import BaseModel, Field

from .. import metrics
from ..gateway import EMBEDDING_DIMS, Gateway
from ..guardrails import UNTRUSTED_NOTICE, clean_text, looks_like_injection, redact_pii, strip_foreign_urls, untrusted

ContentType = Literal['posts', 'listings', 'groups', 'pages', 'videos']
MAX_EMBED_TEXTS = 64
MAX_EMBED_CHARS = 8000


# ── Embeddings ──────────────────────────────────────────────────────────────

class EmbedRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=MAX_EMBED_TEXTS)


class EmbedResult(BaseModel):
    vectors: list[list[float]]
    model: str
    dims: int


async def embed(req: EmbedRequest, gateway: Gateway, user_id: int) -> EmbedResult:
    texts = [clean_text(t, MAX_EMBED_CHARS) or ' ' for t in req.texts]
    res = await gateway.embed('search.embed', texts=texts, user_id=user_id)
    return EmbedResult(vectors=res.vectors, model=res.model, dims=EMBEDDING_DIMS)


# ── Query understanding ─────────────────────────────────────────────────────

class QueryPlan(BaseModel):
    query: str = Field(max_length=200, description='The search intent restated as a short keyword-rich query.')
    types: list[ContentType] = Field(
        max_length=5, description='Content types the user is looking for. Empty means any type.')
    since_days: int | None = Field(
        default=None, ge=1, le=3650, description='Only content from the last N days, when the query says so.')
    author: str | None = Field(default=None, max_length=150, description='A person the query names as author.')


class QueryRequest(BaseModel):
    q: str = Field(min_length=1, max_length=200)
    rewrite: bool = True


class QueryResult(BaseModel):
    plan: QueryPlan
    vector: list[float]
    rewritten: bool


REWRITE_SYSTEM = f"""You turn a social-network search box query into a search plan.
{UNTRUSTED_NOTICE}

- "query": restate the intent as a short query using the words likely to appear in matching posts,
  listings, groups, pages or videos. Keep names, places and product words. Expand obvious slang and
  abbreviations (e.g. "Joburg" -> "Johannesburg Joburg").
- "types": fill in only when the query clearly asks for something specific ("couch for sale" -> listings,
  "running club" -> groups and posts). Otherwise leave it empty.
- "since_days": only when the query mentions time ("last week" -> 7, "this month" -> 31).
- "author": only when the query names who wrote something ("Thandi's post about ...")."""


async def plan_query(req: QueryRequest, gateway: Gateway, user_id: int) -> QueryResult:
    plan = QueryPlan(query=clean_text(req.q, 200), types=[])
    rewritten = False
    if req.rewrite:
        res = await gateway.structured('search.rewrite', system=REWRITE_SYSTEM,
                                       user=untrusted(req.q, 200, kind='search_query'),
                                       schema=QueryPlan, user_id=user_id)
        plan = res.output
        plan.query = plan.query.strip() or clean_text(req.q, 200)
        rewritten = True
    # Embed the original words plus the rewrite: the rewrite helps recall, the
    # original keeps intent if the rewrite drifted.
    text = req.q if not rewritten or plan.query == req.q else f'{req.q}\n{plan.query}'
    emb = await gateway.embed('search.embed', texts=[text], user_id=user_id)
    return QueryResult(plan=plan, vector=emb.vectors[0], rewritten=rewritten)


# ── Rerank ──────────────────────────────────────────────────────────────────

class Candidate(BaseModel):
    id: str = Field(max_length=40, pattern=r'^[a-z]+:\d+$')
    text: str = Field(max_length=4000)


class RerankRequest(BaseModel):
    query: str = Field(max_length=200)
    candidates: list[Candidate] = Field(min_length=1, max_length=50)


class Ranking(BaseModel):
    ids: list[str] = Field(max_length=50, description='Candidate ids, most relevant first. Omit irrelevant ones.')


class RerankResult(BaseModel):
    ids: list[str]
    model: str


RERANK_SYSTEM = f"""You rank search results for relevance to a query.
{UNTRUSTED_NOTICE}
Return the ids of the relevant candidates, most relevant first. Leave out candidates that don't match
the query at all. Use only ids that appear in the input."""


async def rerank(req: RerankRequest, gateway: Gateway, user_id: int) -> RerankResult:
    body = '\n'.join([f'Query: {clean_text(req.query, 200)}', ''] +
                     [untrusted(c.text, 600, id=c.id) for c in req.candidates])
    res = await gateway.structured('search.rerank', system=RERANK_SYSTEM, user=body, schema=Ranking,
                                   user_id=user_id)
    valid = {c.id for c in req.candidates}
    ids = [i for i in dict.fromkeys(res.output.ids) if i in valid]
    return RerankResult(ids=ids, model=res.model)


# ── Grounded answers ────────────────────────────────────────────────────────

class Source(BaseModel):
    id: str = Field(max_length=40, pattern=r'^[a-z]+:\d+$')
    kind: str = Field(max_length=20)
    title: str = Field(default='', max_length=200)
    author: str = Field(default='', max_length=150)
    created_at: str = Field(default='', max_length=40)
    text: str = Field(max_length=6000)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    viewer: str = Field(max_length=150)
    sources: list[Source] = Field(max_length=12)


class Claim(BaseModel):
    text: str = Field(max_length=500)
    source_ids: list[str] = Field(max_length=6)


class Answer(BaseModel):
    abstain: bool = Field(description='True when the sources do not answer the question.')
    answer: str = Field(max_length=1200, description='A short direct answer, or why it cannot be answered.')
    claims: list[Claim] = Field(max_length=8, description='Each supporting statement with the ids it came from.')


class AskResult(BaseModel):
    answer: Answer
    model: str
    cost_usd: float
    citations_dropped: int


ASK_SYSTEM = f"""You answer a member's question using only the posts, listings, groups, pages and videos
provided as sources. These are things the member is allowed to see on the social network.
{UNTRUSTED_NOTICE}

Rules:
- Use only facts stated in the sources. Never use outside knowledge about the people or places.
- Every claim must cite the ids of the sources it comes from.
- If the sources don't answer the question, set "abstain" to true and say briefly what you couldn't find.
- Keep the answer short and plain. No links, phone numbers or contact details unless a source contains them."""


def verify_answer(answer: Answer, valid_ids: set[str], sources_text: str) -> int:
    dropped = 0
    kept = []
    for c in answer.claims:
        good = [i for i in dict.fromkeys(c.source_ids) if i in valid_ids]
        dropped += len(c.source_ids) - len(good)
        metrics.ATTRIBUTION.labels('true').inc(len(good))
        metrics.ATTRIBUTION.labels('false').inc(len(c.source_ids) - len(good))
        if good:
            c.source_ids = good
            c.text = strip_foreign_urls(c.text, sources_text)
            kept.append(c)
    answer.claims = kept
    answer.answer = strip_foreign_urls(answer.answer, sources_text)
    # An answer with no surviving citation is unsupported.
    if not answer.claims and not answer.abstain:
        answer.abstain = True
        answer.answer = "I couldn't find anything you can see that answers that."
    return dropped


async def ask(req: AskRequest, gateway: Gateway, user_id: int) -> AskResult:
    if not req.sources:
        return AskResult(answer=Answer(abstain=True, answer="I couldn't find anything you can see that answers that.",
                                       claims=[]), model='none', cost_usd=0.0, citations_dropped=0)
    # Sources that try to instruct the model are dropped before it sees them.
    sources = [s for s in req.sources if not looks_like_injection(s.text)]
    metrics.INJECTION_DROPS.inc(len(req.sources) - len(sources))
    if not sources:
        return AskResult(answer=Answer(abstain=True, answer="I couldn't find anything you can see that answers that.",
                                       claims=[]), model='none', cost_usd=0.0, citations_dropped=0)
    lines = [f'Member: {clean_text(req.viewer, 150)}', f'Question: {clean_text(req.question, 500)}', '', 'Sources:']
    for s in sources:
        lines.append(untrusted(redact_pii(s.text), 3000, id=s.id, kind=s.kind, title=s.title[:60], author=s.author,
                               at=s.created_at))
    res = await gateway.structured('ask.answer', system=ASK_SYSTEM, user='\n'.join(lines), schema=Answer,
                                   user_id=user_id)
    dropped = verify_answer(res.output, {s.id for s in sources}, '\n'.join(s.text for s in sources))
    return AskResult(answer=res.output, model=res.model, cost_usd=round(res.cost_usd, 6), citations_dropped=dropped)
