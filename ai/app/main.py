import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .auth import ActingUser, acting_user
from .budget import Budget
from .config import get_settings
from .features.catchup import CatchUpRequest, CatchUpResult, catch_up
from .features.moderation import ModerationRequest, ModerationResult, moderate
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
    return Gateway(providers=providers, budget=Budget(s.daily_user_token_budget, s.redis_url)), openai_provider


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.gateway, app.state.moderation_stage0 = build_gateway()
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


@app.post('/v1/catchup', response_model=CatchUpResult)
async def catchup_endpoint(body: CatchUpRequest, request: Request, user: ActingUser = Depends(acting_user)):
    try:
        return await catch_up(body, request.app.state.gateway, user.id)
    except BudgetExceeded:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, 'Daily AI allowance used up') from None
    except Refused:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'The model declined to summarise this chat') from None
    except AllRoutesFailed:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, 'AI is temporarily unavailable') from None
