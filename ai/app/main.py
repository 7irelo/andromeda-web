import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import PlainTextResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .auth import ActingUser, acting_user
from .budget import Budget
from .config import get_settings
from .features.catchup import CatchUpRequest, CatchUpResult, catch_up
from .features.listing import DraftRequest, DraftResult, draft
from .features.moderation import ModerationRequest, ModerationResult, moderate
from .features.speech import (DeepgramClient, SpeakRequest, SpeechUnavailable, TranscribeRequest, TranscribeResult,
                              transcribe)
from .features.retrieval import (AskRequest, AskResult, EmbedRequest, EmbedResult, QueryRequest, QueryResult,
                                 RerankRequest, RerankResult, ask, embed, plan_query, rerank)
from .gateway import AllRoutesFailed, BudgetExceeded, Gateway, Refused
from .providers import AnthropicProvider, OpenAIProvider

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s %(message)s')


def build_gateway() -> tuple[Gateway, OpenAIProvider | None]:
    s = get_settings()
    providers = {}
    openai_provider = None
    if s.anthropic_api_key:
        providers['anthropic'] = AnthropicProvider(s.anthropic_api_key.get_secret_value(), s.provider_timeout_seconds)
    if s.openai_api_key:
        openai_provider = OpenAIProvider(s.openai_api_key.get_secret_value(), s.provider_timeout_seconds)
        providers['openai'] = openai_provider
    budget = Budget(s.daily_user_token_budget, s.redis_url, s.system_daily_token_budget, s.daily_user_audio_seconds)
    return Gateway(providers=providers, budget=budget), openai_provider


def build_speech() -> DeepgramClient | None:
    s = get_settings()
    return DeepgramClient(s.deepgram_api_key.get_secret_value()) if s.deepgram_api_key else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.gateway, app.state.moderation_stage0 = build_gateway()
    app.state.speech = build_speech()
    yield


# No interactive docs: this is an internal service.
app = FastAPI(title='Andromeda AI', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.get('/healthz')
def healthz():
    return {'status': 'ok'}


@app.get('/metrics', include_in_schema=False)
def prometheus_metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post('/v1/moderate', response_model=ModerationResult)
async def moderate_endpoint(body: ModerationRequest, request: Request, user: ActingUser = Depends(acting_user)):
    return await moderate(body, request.app.state.gateway, user.id, request.app.state.moderation_stage0)


async def _run(coro, refused_detail='The model declined this request'):
    """Map gateway failures to HTTP errors Django understands."""
    try:
        return await coro
    except BudgetExceeded:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, 'Daily AI allowance used up') from None
    except Refused:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, refused_detail) from None
    except AllRoutesFailed:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, 'AI is temporarily unavailable') from None


@app.post('/v1/catchup', response_model=CatchUpResult)
async def catchup_endpoint(body: CatchUpRequest, request: Request, user: ActingUser = Depends(acting_user)):
    return await _run(catch_up(body, request.app.state.gateway, user.id), 'The model declined to summarise this chat')


@app.post('/v1/embed', response_model=EmbedResult)
async def embed_endpoint(body: EmbedRequest, request: Request, user: ActingUser = Depends(acting_user)):
    return await _run(embed(body, request.app.state.gateway, user.id))


@app.post('/v1/search/plan', response_model=QueryResult)
async def search_plan_endpoint(body: QueryRequest, request: Request, user: ActingUser = Depends(acting_user)):
    return await _run(plan_query(body, request.app.state.gateway, user.id))


@app.post('/v1/search/rerank', response_model=RerankResult)
async def rerank_endpoint(body: RerankRequest, request: Request, user: ActingUser = Depends(acting_user)):
    return await _run(rerank(body, request.app.state.gateway, user.id))


@app.post('/v1/ask', response_model=AskResult)
async def ask_endpoint(body: AskRequest, request: Request, user: ActingUser = Depends(acting_user)):
    return await _run(ask(body, request.app.state.gateway, user.id), 'The model declined to answer that')


@app.post('/v1/listing/draft', response_model=DraftResult)
async def listing_draft_endpoint(body: DraftRequest, request: Request, user: ActingUser = Depends(acting_user)):
    return await _run(draft(body, request.app.state.gateway, user.id), 'The model declined to describe these photos')


@app.post('/v1/transcribe', response_model=TranscribeResult)
async def transcribe_endpoint(body: TranscribeRequest, request: Request, user: ActingUser = Depends(acting_user)):
    try:
        return await transcribe(body, request.app.state.speech, request.app.state.gateway.budget, user.id)
    except SpeechUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, 'Speech is temporarily unavailable') from None


@app.post('/v1/speak')
async def speak_endpoint(body: SpeakRequest, request: Request, user: ActingUser = Depends(acting_user)):
    client = request.app.state.speech
    if client is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, 'Speech is not configured')
    try:
        audio = await client.speak(body.text)
    except SpeechUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, 'Speech is temporarily unavailable') from None
    return Response(audio, media_type='audio/mpeg')
