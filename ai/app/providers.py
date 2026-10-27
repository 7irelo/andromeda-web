"""Provider adapters over the official Anthropic and OpenAI SDKs."""
import anthropic
import openai

from .gateway import ProviderError, Refused, Route, T, Usage


class AnthropicProvider:
    name = 'anthropic'

    def __init__(self, api_key: str, timeout: float):
        self.client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=1)

    async def structured(self, route: Route, system: str, user: str, schema: type[T]) -> tuple[T, Usage]:
        kwargs = {}
        if route.effort:
            kwargs['output_config'] = {'effort': route.effort}
        try:
            msg = await self.client.messages.parse(
                model=route.model,
                max_tokens=route.max_tokens,
                # The system prompt is the stable prefix, so it's cached across calls.
                system=[{'type': 'text', 'text': system, 'cache_control': {'type': 'ephemeral'}}],
                messages=[{'role': 'user', 'content': user}],
                output_format=schema,
                **kwargs,
            )
        except (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIConnectionError,
                anthropic.APITimeoutError) as exc:
            raise ProviderError(type(exc).__name__) from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500 or exc.status_code == 529:
                raise ProviderError(f'HTTP {exc.status_code}') from exc
            raise
        if msg.stop_reason == 'refusal':
            raise Refused(getattr(msg.stop_details, 'category', None) or 'refusal')
        if msg.stop_reason == 'max_tokens' or msg.parsed_output is None:
            raise ProviderError(f'Incomplete output ({msg.stop_reason})')
        u = msg.usage
        return msg.parsed_output, Usage(u.input_tokens + (u.cache_read_input_tokens or 0)
                                        + (u.cache_creation_input_tokens or 0),
                                        u.output_tokens, u.cache_read_input_tokens or 0)


class OpenAIProvider:
    name = 'openai'

    def __init__(self, api_key: str, timeout: float):
        self.client = openai.AsyncOpenAI(api_key=api_key, timeout=timeout, max_retries=1)

    async def structured(self, route: Route, system: str, user: str, schema: type[T]) -> tuple[T, Usage]:
        try:
            resp = await self.client.responses.parse(
                model=route.model,
                instructions=system,
                input=user,
                text_format=schema,
                max_output_tokens=route.max_tokens,
                store=False,  # don't retain user content on the provider side
            )
        except (openai.RateLimitError, openai.InternalServerError, openai.APIConnectionError,
                openai.APITimeoutError) as exc:
            raise ProviderError(type(exc).__name__) from exc
        parsed = resp.output_parsed
        if parsed is None:
            raise ProviderError('No parsed output')
        u = resp.usage
        cached = getattr(getattr(u, 'input_tokens_details', None), 'cached_tokens', 0) or 0
        return parsed, Usage(u.input_tokens, u.output_tokens, cached)

    async def moderate(self, text: str) -> dict:
        """OpenAI's free moderation endpoint (stage 0)."""
        try:
            res = await self.client.moderations.create(model='omni-moderation-latest', input=text)
        except (openai.RateLimitError, openai.InternalServerError, openai.APIConnectionError,
                openai.APITimeoutError) as exc:
            raise ProviderError(type(exc).__name__) from exc
        r = res.results[0]
        scores = r.category_scores.model_dump()
        return {'flagged': r.flagged, 'top_category': max(scores, key=scores.get), 'top_score': max(scores.values()),
                'categories': [k for k, v in r.categories.model_dump().items() if v]}
