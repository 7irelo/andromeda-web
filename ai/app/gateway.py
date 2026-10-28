"""
Model gateway: one interface for every model call.

- Routes each job to a primary model with an ordered fallback chain
  (Anthropic first, OpenAI as the cross-provider fallback).
- Fails over on rate limits, server errors, timeouts and open circuits;
  never on bad requests, which would fail the same way everywhere.
- Meters tokens and estimated cost per job, model and user, and enforces the
  per-user daily budget before any call is made.
- Traces every attempt as an OpenTelemetry span with the GenAI semantic
  conventions (system, model, token usage) plus ``ai.job``, ``ai.cost_usd``
  and ``ai.prompt_hash``. Prompts and responses never go into spans: the hash
  is an HMAC keyed with the service secret, so it can group identical prompts
  without being reversible by guessing.
"""
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Protocol, TypeVar

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from pydantic import BaseModel

from . import metrics
from .budget import Budget

logger = logging.getLogger(__name__)
tracer = trace.get_tracer('andromeda.ai.gateway')
T = TypeVar('T', bound=BaseModel)


@dataclass(frozen=True)
class Route:
    provider: str          # 'anthropic' | 'openai'
    model: str
    max_tokens: int = 1024
    effort: str | None = 'low'


# Per-job routing. Primary first, fallbacks after. See the model-selection
# table in the AI plan for the reasoning behind each choice.
ROUTES: dict[str, list[Route]] = {
    'moderation.classify': [Route('anthropic', 'claude-haiku-5-5', 1024),
                            Route('openai', 'gpt-6-luna', 1024, None)],
    'moderation.escalate': [Route('anthropic', 'claude-sonnet-5-5', 2048),
                            Route('openai', 'gpt-6.1-terra', 2048, None)],
    'catchup.summarise': [Route('anthropic', 'claude-haiku-5-5', 4096),
                          Route('openai', 'gpt-6.1-terra', 4096, None)],
    'search.rewrite': [Route('anthropic', 'claude-haiku-5-5', 512),
                       Route('openai', 'gpt-6-luna', 512, None)],
    'search.rerank': [Route('anthropic', 'claude-haiku-5-5', 1024),
                      Route('openai', 'gpt-6-luna', 1024, None)],
    'ask.answer': [Route('anthropic', 'claude-sonnet-5-5', 2048),
                   Route('openai', 'gpt-6.1-terra', 2048, None)],
    # Vision: reading brands, models and wear from photos needs the stronger model.
    'listing.draft': [Route('anthropic', 'claude-sonnet-5-5', 1500),
                      Route('openai', 'gpt-6.1-terra', 1500, None)],
    'video.chapters': [Route('anthropic', 'claude-haiku-5-5', 1024),
                       Route('openai', 'gpt-6-luna', 1024, None)],
    # Anthropic has no embeddings model, so this job has no cross-provider fallback.
    'search.embed': [Route('openai', 'text-embedding-3-small', 0, None)],
}

EMBEDDING_DIMS = 1536

# USD per 1M tokens (input, output), standard list prices, checked 2026-10-27.
PRICES = {
    'claude-haiku-5-5': (0.10, 0.50),
    'claude-sonnet-5-5': (2.00, 10.00),
    'claude-opus-5-5': (4.00, 20.00),
    'gpt-6-luna': (0.10, 0.50),
    'gpt-6.1-terra': (1.00, 5.00),
    'text-embedding-3-small': (0.02, 0.0),
}


class ProviderError(Exception):
    """Transient failure: try the next route."""


class Refused(Exception):
    """The model declined; callers decide what that means (e.g. send to review)."""


class BudgetExceeded(Exception):
    pass


class AllRoutesFailed(Exception):
    pass


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class Result[T]:
    output: T
    model: str
    provider: str
    usage: Usage
    cost_usd: float
    latency_s: float
    fallback_used: bool = False


@dataclass
class EmbedResult:
    vectors: list[list[float]]
    model: str
    usage: Usage
    cost_usd: float


# A user turn is plain text, or a list of parts for multimodal input:
#   {'type': 'text', 'text': ...} | {'type': 'image', 'media_type': 'image/jpeg', 'data': <base64>}
UserContent = str | list[dict]


class Provider(Protocol):
    name: str

    async def structured(self, route: Route, system: str, user: UserContent, schema: type[T]) -> tuple[T, Usage]: ...


@dataclass
class CircuitBreaker:
    threshold: int = 5
    cooldown_s: float = 30.0
    failures: int = 0
    opened_at: float = 0.0

    def available(self) -> bool:
        if self.failures < self.threshold:
            return True
        if time.monotonic() - self.opened_at > self.cooldown_s:
            self.failures = self.threshold - 1  # half-open: allow one probe
            return True
        return False

    def record(self, ok: bool) -> None:
        if ok:
            self.failures = 0
        else:
            self.failures += 1
            if self.failures >= self.threshold:
                self.opened_at = time.monotonic()


def estimate_cost(model: str, usage: Usage) -> float:
    price_in, price_out = PRICES.get(model, (0.0, 0.0))
    return (usage.input_tokens * price_in + usage.output_tokens * price_out) / 1_000_000


def prompt_hash(key: bytes, *parts) -> str:
    """Keyed, truncated hash of the prompt for spans; the text itself is never recorded."""
    raw = json.dumps(parts, sort_keys=True, default=str, separators=(',', ':')).encode()
    return hmac.new(key, raw, hashlib.sha256).hexdigest()[:32]


def _start_span(operation: str, job: str, route: Route, phash: str, attempt: int):
    span = tracer.start_span(f'{operation} {route.model}', kind=SpanKind.CLIENT)
    if span.is_recording():
        span.set_attributes({
            'gen_ai.operation.name': operation,
            'gen_ai.system': route.provider,
            'gen_ai.provider.name': route.provider,
            'gen_ai.request.model': route.model,
            'ai.job': job,
            'ai.prompt_hash': phash,
            'ai.attempt': attempt,
        })
        if route.max_tokens:
            span.set_attribute('gen_ai.request.max_tokens', route.max_tokens)
    return span


def _end_span(span, *, usage: Usage | None = None, cost: float | None = None, error: str | None = None,
              outcome: str = 'ok') -> None:
    if span.is_recording():
        span.set_attribute('ai.outcome', outcome)
        if usage is not None:
            span.set_attributes({
                'gen_ai.usage.input_tokens': usage.input_tokens,
                'gen_ai.usage.output_tokens': usage.output_tokens,
                'ai.cost_usd': round(cost or 0.0, 8),
            })
        if error:
            # The exception type only: provider messages can echo request content.
            span.set_attribute('error.type', error)
            span.set_status(Status(StatusCode.ERROR, error))
    span.end()


@dataclass
class Gateway:
    providers: dict[str, Provider]
    budget: Budget
    routes: dict[str, list[Route]] = field(default_factory=lambda: ROUTES)
    breakers: dict[str, CircuitBreaker] = field(default_factory=dict)
    prompt_hash_key: bytes = b''

    def _check_budget(self, job: str, user_id: int) -> None:
        if not self.budget.has_room(user_id):
            metrics.BUDGET_REJECTIONS.labels(job).inc()
            raise BudgetExceeded(job)

    def _meter(self, job: str, route: Route, usage: Usage, latency: float, user_id: int, fallback: bool) -> float:
        cost = estimate_cost(route.model, usage)
        self.budget.spend(user_id, usage.total)
        metrics.REQUESTS.labels(job, route.provider, route.model, 'ok').inc()
        metrics.TOKENS.labels(job, route.model, 'input').inc(usage.input_tokens)
        metrics.TOKENS.labels(job, route.model, 'output').inc(usage.output_tokens)
        metrics.TOKENS.labels(job, route.model, 'cache_read').inc(usage.cache_read_tokens)
        metrics.COST.labels(job, route.model).inc(cost)
        metrics.LATENCY.labels(job, route.model).observe(latency)
        if fallback:
            metrics.FALLBACKS.labels(job).inc()
        return cost

    def _candidates(self, job: str):
        for i, route in enumerate(self.routes[job]):
            provider = self.providers.get(route.provider)
            breaker = self.breakers.setdefault(route.provider, CircuitBreaker())
            if provider is None or not breaker.available():
                continue
            yield i, route, provider, breaker

    async def embed(self, job: str, *, texts: list[str], user_id: int) -> EmbedResult:
        self._check_budget(job, user_id)
        last_error: Exception | None = None
        phash = prompt_hash(self.prompt_hash_key, texts)
        for i, route, provider, breaker in self._candidates(job):
            started = time.monotonic()
            span = _start_span('embeddings', job, route, phash, i)
            try:
                # No record_exception: provider errors can echo prompt text.
                with trace.use_span(span, end_on_exit=False, record_exception=False, set_status_on_exception=False):
                    vectors, usage = await provider.embed(route, texts)
            except ProviderError as exc:
                breaker.record(False)
                metrics.REQUESTS.labels(job, route.provider, route.model, 'error').inc()
                _end_span(span, error=type(exc).__name__, outcome='error')
                last_error = exc
                continue
            breaker.record(True)
            cost = self._meter(job, route, usage, time.monotonic() - started, user_id, i > 0)
            _end_span(span, usage=usage, cost=cost)
            return EmbedResult(vectors, route.model, usage, cost)
        raise AllRoutesFailed(job) from last_error

    async def structured(self, job: str, *, system: str, user: UserContent, schema: type[T],
                         user_id: int) -> Result[T]:
        self._check_budget(job, user_id)
        last_error: Exception | None = None
        phash = prompt_hash(self.prompt_hash_key, system, user)
        for i, route, provider, breaker in self._candidates(job):
            started = time.monotonic()
            span = _start_span('chat', job, route, phash, i)
            try:
                # No record_exception: provider errors can echo prompt text.
                with trace.use_span(span, end_on_exit=False, record_exception=False, set_status_on_exception=False):
                    output, usage = await provider.structured(route, system, user, schema)
            except Refused:
                breaker.record(True)
                metrics.REQUESTS.labels(job, route.provider, route.model, 'refused').inc()
                _end_span(span, outcome='refused')
                raise
            except ProviderError as exc:
                breaker.record(False)
                metrics.REQUESTS.labels(job, route.provider, route.model, 'error').inc()
                logger.warning('Route %s/%s failed for %s: %s', route.provider, route.model, job, exc)
                _end_span(span, error=type(exc).__name__, outcome='error')
                last_error = exc
                continue
            latency = time.monotonic() - started
            breaker.record(True)
            cost = self._meter(job, route, usage, latency, user_id, i > 0)
            _end_span(span, usage=usage, cost=cost)
            return Result(output, route.model, route.provider, usage, cost, latency, fallback_used=i > 0)
        raise AllRoutesFailed(job) from last_error
