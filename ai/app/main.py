import json
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import PlainTextResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .auth import ActingUser, acting_user, verify_token
from .budget import Budget
from .config import get_settings
from .features.assistant import (DraftRequest as AssistantDraftRequest, DraftResult as AssistantDraftResult,
                                 RouteRequest, RouteResult, StepRequest, StepResult, draft as assistant_draft, route,
                                 step)
from .features.catchup import CatchUpRequest, CatchUpResult, catch_up
from .features.listing import DraftRequest, DraftResult, draft
from .features.chapters import ChaptersRequest, ChaptersResult, chapters
from .features import distilled, voice
from .features.compose import ComposeRequest, ComposeResult, rewrite
from .features.query_cache import QueryCache
from .features.moderation import ModerationRequest, ModerationResult, moderate
from .features.replies import RepliesRequest, RepliesResult, suggest
from .features.speech import (DeepgramClient, SpeakRequest, SpeechUnavailable, TranscribeRequest, TranscribeResult,
                              transcribe)
from .features.retrieval import (AskRequest, AskResult, EmbedRequest, EmbedResult, QueryRequest, QueryResult,
                                 RerankRequest, RerankResult, ask, embed, plan_query, rerank)
from .gateway import AllRoutesFailed, BudgetExceeded, Gateway, Refused
from .observability import RequestIdMiddleware, setup_errors, setup_logging, setup_tracing
from .providers import AnthropicProvider, OpenAIProvider, VLLMProvider

setup_logging()
setup_errors()
logger = logging.getLogger(__name__)


def build_gateway() -> tuple[Gateway, OpenAIProvider | None]:
    s = get_settings()
    providers = {}
    openai_provider = None
    if s.anthropic_api_key:
        providers['anthropic'] = AnthropicProvider(s.anthropic_api_key.get_secret_value(), s.provider_timeout_seconds)
    if s.openai_api_key:
        openai_provider = OpenAIProvider(s.openai_api_key.get_secret_value(), s.provider_timeout_seconds)
        providers['openai'] = openai_provider
    if s.vllm_base_url:
        key = s.vllm_api_key.get_secret_value() if s.vllm_api_key else None
        providers['vllm'] = VLLMProvider(s.vllm_base_url, s.provider_timeout_seconds, key)
    budget = Budget(s.daily_user_token_budget, s.redis_url, s.system_daily_token_budget, s.daily_user_audio_seconds)
    return (Gateway(providers=providers, budget=budget,
                    prompt_hash_key=s.ai_service_secret.get_secret_value().encode()), openai_provider)


def build_speech() -> DeepgramClient | None:
    s = get_settings()
    return DeepgramClient(s.deepgram_api_key.get_secret_value()) if s.deepgram_api_key else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.gateway, app.state.moderation_stage0 = build_gateway()
    app.state.speech = build_speech()
    app.state.query_cache = QueryCache()
    app.state.moderation_student = distilled.load(get_settings().moderation_student_path)
    yield


# No interactive docs: this is an internal service.
app = FastAPI(title='Andromeda AI', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(RequestIdMiddleware)
setup_tracing(app)


@app.get('/healthz')
def healthz():
    return {'status': 'ok'}


@app.get('/metrics', include_in_schema=False)
def prometheus_metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post('/v1/moderate', response_model=ModerationResult)
async def moderate_endpoint(body: ModerationRequest, request: Request, user: ActingUser = Depends(acting_user)):
    return await moderate(body, request.app.state.gateway, user.id, request.app.state.moderation_stage0,
                          request.app.state.moderation_student)


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
    return await _run(plan_query(body, request.app.state.gateway, user.id, request.app.state.query_cache))


@app.post('/v1/search/rerank', response_model=RerankResult)
async def rerank_endpoint(body: RerankRequest, request: Request, user: ActingUser = Depends(acting_user)):
    return await _run(rerank(body, request.app.state.gateway, user.id))


@app.post('/v1/ask', response_model=AskResult)
async def ask_endpoint(body: AskRequest, request: Request, user: ActingUser = Depends(acting_user)):
    return await _run(ask(body, request.app.state.gateway, user.id), 'The model declined to answer that')


@app.post('/v1/listing/draft', response_model=DraftResult)
async def listing_draft_endpoint(body: DraftRequest, request: Request, user: ActingUser = Depends(acting_user)):
    return await _run(draft(body, request.app.state.gateway, user.id), 'The model declined to describe these photos')


@app.post('/v1/video/chapters', response_model=ChaptersResult)
async def chapters_endpoint(body: ChaptersRequest, request: Request, user: ActingUser = Depends(acting_user)):
    return await _run(chapters(body, request.app.state.gateway, user.id), 'The model declined to chapter this video')


@app.post('/v1/replies', response_model=RepliesResult)
async def replies_endpoint(body: RepliesRequest, request: Request, user: ActingUser = Depends(acting_user)):
    return await _run(suggest(body, request.app.state.gateway, user.id, request.app.state.moderation_stage0),
                      'The model declined to suggest replies')


@app.post('/v1/compose', response_model=ComposeResult)
async def compose_endpoint(body: ComposeRequest, request: Request, user: ActingUser = Depends(acting_user)):
    return await _run(rewrite(body, request.app.state.gateway, user.id), 'The model declined to rewrite this')


@app.post('/v1/transcribe', response_model=TranscribeResult)
async def transcribe_endpoint(body: TranscribeRequest, request: Request, user: ActingUser = Depends(acting_user)):
    try:
        return await transcribe(body, request.app.state.speech, request.app.state.gateway.budget, user.id)
    except SpeechUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, 'Speech is temporarily unavailable') from None


@app.websocket('/v1/voice')
async def voice_endpoint(ws: WebSocket, engine: str = 'cascaded'):
    """Realtime voice. Only Django connects here, with the same service token as every other call."""
    settings = get_settings()
    scheme, _, token = ws.headers.get('authorization', '').partition(' ')
    try:
        if scheme.lower() != 'bearer':
            raise HTTPException(status.HTTP_401_UNAUTHORIZED)
        user = verify_token(token, settings)
    except HTTPException:
        await ws.close(code=4401)
        return
    gateway = ws.app.state.gateway
    if not gateway.budget.has_audio_room(user.id) or not gateway.budget.has_room(user.id):
        await ws.close(code=4429)
        return
    await ws.accept()

    class Peer:
        send_json = staticmethod(ws.send_json)
        send_bytes = staticmethod(ws.send_bytes)

    async def receive():
        message = await ws.receive()
        if message['type'] == 'websocket.disconnect':
            return None
        if message.get('bytes') is not None:
            return message['bytes']
        return json.loads(message.get('text') or '{}')

    def secret(key):
        return key.get_secret_value() if key else None

    try:
        start = await ws.receive_json()
        tools = start.get('tools') if isinstance(start, dict) else None
        built = voice.build_engine(engine, Peer, gateway, user.id, tools if isinstance(tools, list) else [],
                                   deepgram_key=secret(settings.deepgram_api_key),
                                   openai_key=secret(settings.openai_api_key))
    except voice.VoiceUnavailable:
        await ws.close(code=4503)
        return
    except (WebSocketDisconnect, ValueError):
        return
    outcome = await voice.run_session(built, receive, gateway.budget)
    if outcome != 'closed':
        try:
            await ws.close(code=4000, reason=outcome)
        except RuntimeError:
            pass  # already closed


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


@app.post('/v1/assistant/route', response_model=RouteResult)
async def assistant_route_endpoint(body: RouteRequest, request: Request, user: ActingUser = Depends(acting_user)):
    return await _run(route(body, request.app.state.gateway, user.id), 'The model declined this request')


@app.post('/v1/assistant/draft', response_model=AssistantDraftResult)
async def assistant_draft_endpoint(body: AssistantDraftRequest, request: Request,
                                   user: ActingUser = Depends(acting_user)):
    return await _run(assistant_draft(body, request.app.state.gateway, user.id), 'The model declined to write this')


@app.post('/v1/assistant/step', response_model=StepResult)
async def assistant_step_endpoint(body: StepRequest, request: Request, user: ActingUser = Depends(acting_user)):
    return await _run(step(body, request.app.state.gateway, user.id), 'The model declined this request')
