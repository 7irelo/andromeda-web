"""Provider adapters over the official Anthropic and OpenAI SDKs, plus an optional self-hosted vLLM."""
import json

import anthropic
import httpx
import openai
from pydantic import ValidationError

from .gateway import ProviderError, Refused, Route, StepOutput, T, ToolCall, Turn, Usage, UserContent

# Content block types replayed from an earlier Anthropic turn; anything else is dropped.
_REPLAY_BLOCKS = {'text', 'thinking', 'redacted_thinking', 'tool_use'}

_TRANSIENT_ANTHROPIC = (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIConnectionError,
                        anthropic.APITimeoutError)
_TRANSIENT_OPENAI = (openai.RateLimitError, openai.InternalServerError, openai.APIConnectionError,
                     openai.APITimeoutError)


def _anthropic_content(user: UserContent):
    if isinstance(user, str):
        return user
    blocks = []
    for part in user:
        if part['type'] == 'image':
            blocks.append({'type': 'image', 'source': {'type': 'base64', 'media_type': part['media_type'],
                                                       'data': part['data']}})
        else:
            blocks.append({'type': 'text', 'text': part['text']})
    return blocks


def _openai_input(user: UserContent):
    if isinstance(user, str):
        return user
    content = []
    for part in user:
        if part['type'] == 'image':
            content.append({'type': 'input_image', 'image_url': f"data:{part['media_type']};base64,{part['data']}"})
        else:
            content.append({'type': 'input_text', 'text': part['text']})
    return [{'role': 'user', 'content': content}]


def _anthropic_turns(turns: list[Turn]) -> list[dict]:
    """Neutral turns to Messages API messages. Earlier Anthropic output is replayed unchanged."""
    out = []
    for t in turns:
        if t['role'] == 'user':
            out.append({'role': 'user', 'content': t['text']})
        elif t['role'] == 'assistant':
            native = t.get('native') or {}
            if native.get('provider') == 'anthropic' and native.get('content'):
                # Thinking blocks must come back exactly as they were produced.
                content = [b for b in native['content'] if isinstance(b, dict) and b.get('type') in _REPLAY_BLOCKS]
            else:
                content = ([{'type': 'text', 'text': t['text']}] if t.get('text') else []) + [
                    {'type': 'tool_use', 'id': c['id'], 'name': c['name'], 'input': c['arguments']}
                    for c in t.get('tool_calls', [])]
            out.append({'role': 'assistant', 'content': content or [{'type': 'text', 'text': '(no reply)'}]})
        else:
            out.append({'role': 'user', 'content': [
                {'type': 'tool_result', 'tool_use_id': r['call_id'], 'content': r['content'],
                 **({'is_error': True} if r.get('is_error') else {})} for r in t['results']]})
    return out


def _openai_turns(turns: list[Turn]) -> list[dict]:
    """Neutral turns to Responses API input items (function_call / function_call_output)."""
    items = []
    for t in turns:
        if t['role'] == 'user':
            items.append({'role': 'user', 'content': t['text']})
        elif t['role'] == 'assistant':
            if t.get('text'):
                items.append({'role': 'assistant', 'content': t['text']})
            for c in t.get('tool_calls', []):
                items.append({'type': 'function_call', 'call_id': c['id'], 'name': c['name'],
                              'arguments': json.dumps(c['arguments'])})
        else:
            for r in t['results']:
                items.append({'type': 'function_call_output', 'call_id': r['call_id'], 'output': r['content']})
    return items


class AnthropicProvider:
    name = 'anthropic'

    def __init__(self, api_key: str, timeout: float):
        self.client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=1)

    async def structured(self, route: Route, system: str, user: UserContent, schema: type[T]) -> tuple[T, Usage]:
        kwargs = {}
        if route.effort:
            kwargs['output_config'] = {'effort': route.effort}
        try:
            msg = await self.client.messages.parse(
                model=route.model,
                max_tokens=route.max_tokens,
                # The system prompt is the stable prefix, so it's cached across calls.
                system=[{'type': 'text', 'text': system, 'cache_control': {'type': 'ephemeral'}}],
                messages=[{'role': 'user', 'content': _anthropic_content(user)}],
                output_format=schema,
                **kwargs,
            )
        except _TRANSIENT_ANTHROPIC as exc:
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


    async def step(self, route: Route, system: str, turns: list[Turn], tools: list[dict]) -> tuple[StepOutput, Usage]:
        kwargs = {}
        if route.effort:
            kwargs['output_config'] = {'effort': route.effort}
        if tools:
            kwargs['tools'] = [{'name': t['name'], 'description': t['description'], 'input_schema': t['input_schema']}
                               for t in tools]
        if route.timeout_s:
            kwargs['timeout'] = route.timeout_s
        try:
            msg = await self.client.messages.create(
                model=route.model,
                max_tokens=route.max_tokens,
                # Tools and the system prompt are static per job, so they're a cached prefix;
                # the top-level breakpoint also caches the growing conversation between steps.
                system=[{'type': 'text', 'text': system, 'cache_control': {'type': 'ephemeral'}}],
                messages=_anthropic_turns(turns),
                cache_control={'type': 'ephemeral'},
                **kwargs,
            )
        except _TRANSIENT_ANTHROPIC as exc:
            raise ProviderError(type(exc).__name__) from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500 or exc.status_code == 529:
                raise ProviderError(f'HTTP {exc.status_code}') from exc
            raise
        if msg.stop_reason == 'refusal':
            raise Refused(getattr(msg.stop_details, 'category', None) or 'refusal')
        if msg.stop_reason == 'max_tokens':
            raise ProviderError('Incomplete output (max_tokens)')
        # Read blocks by type: a response can start with (empty) thinking blocks.
        text = ''.join(b.text for b in msg.content if b.type == 'text')
        calls = [ToolCall(b.id, b.name, dict(b.input or {})) for b in msg.content if b.type == 'tool_use']
        native = {'provider': 'anthropic', 'model': route.model,
                  'content': [b.to_dict(mode='json') for b in msg.content]}
        u = msg.usage
        usage = Usage(u.input_tokens + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0),
                      u.output_tokens, u.cache_read_input_tokens or 0)
        return StepOutput(text, calls, native, 'tool_use' if calls else 'end'), usage


class OpenAIProvider:
    name = 'openai'

    def __init__(self, api_key: str, timeout: float):
        self.client = openai.AsyncOpenAI(api_key=api_key, timeout=timeout, max_retries=1)

    async def structured(self, route: Route, system: str, user: UserContent, schema: type[T]) -> tuple[T, Usage]:
        try:
            resp = await self.client.responses.parse(
                model=route.model,
                instructions=system,
                input=_openai_input(user),
                text_format=schema,
                max_output_tokens=route.max_tokens,
                store=False,  # don't retain user content on the provider side
            )
        except _TRANSIENT_OPENAI as exc:
            raise ProviderError(type(exc).__name__) from exc
        parsed = resp.output_parsed
        if parsed is None:
            raise ProviderError('No parsed output')
        u = resp.usage
        cached = getattr(getattr(u, 'input_tokens_details', None), 'cached_tokens', 0) or 0
        return parsed, Usage(u.input_tokens, u.output_tokens, cached)

    async def step(self, route: Route, system: str, turns: list[Turn], tools: list[dict]) -> tuple[StepOutput, Usage]:
        kwargs = {}
        if tools:
            kwargs['tools'] = [{'type': 'function', 'name': t['name'], 'description': t['description'],
                                'parameters': t['input_schema'], 'strict': False} for t in tools]
        if route.timeout_s:
            kwargs['timeout'] = route.timeout_s
        try:
            resp = await self.client.responses.create(
                model=route.model,
                instructions=system,
                input=_openai_turns(turns),
                max_output_tokens=route.max_tokens,
                store=False,
                **kwargs,
            )
        except _TRANSIENT_OPENAI as exc:
            raise ProviderError(type(exc).__name__) from exc
        calls, text = [], []
        for item in resp.output or []:
            if item.type == 'function_call':
                try:
                    args = json.loads(item.arguments or '{}')
                except ValueError:
                    args = None
                # Unparseable arguments reach Django as an invalid call, which returns a readable error.
                calls.append(ToolCall(item.call_id, item.name, args if isinstance(args, dict) else {'_invalid': True}))
            elif item.type == 'message':
                text.extend(part.text for part in item.content if getattr(part, 'type', '') == 'output_text')
        if getattr(resp, 'status', None) == 'incomplete' and not calls:
            raise ProviderError('Incomplete output')
        u = resp.usage
        cached = getattr(getattr(u, 'input_tokens_details', None), 'cached_tokens', 0) or 0
        return StepOutput(''.join(text), calls, None, 'tool_use' if calls else 'end'), Usage(
            u.input_tokens, u.output_tokens, cached)

    async def embed(self, route: Route, texts: list[str]) -> tuple[list[list[float]], Usage]:
        try:
            res = await self.client.embeddings.create(model=route.model, input=texts)
        except _TRANSIENT_OPENAI as exc:
            raise ProviderError(type(exc).__name__) from exc
        vectors = [d.embedding for d in sorted(res.data, key=lambda d: d.index)]
        return vectors, Usage(res.usage.prompt_tokens, 0, 0)

    async def moderate(self, text: str) -> dict:
        """OpenAI's free moderation endpoint (stage 0)."""
        try:
            res = await self.client.moderations.create(model='omni-moderation-latest', input=text)
        except _TRANSIENT_OPENAI as exc:
            raise ProviderError(type(exc).__name__) from exc
        r = res.results[0]
        scores = r.category_scores.model_dump()
        return {'flagged': r.flagged, 'top_category': max(scores, key=scores.get), 'top_score': max(scores.values()),
                'categories': [k for k, v in r.categories.model_dump().items() if v]}


class VLLMProvider:
    """
    A self-hosted open model behind vLLM's OpenAI-compatible server (multi-LoRA:
    ``route.model`` names the adapter). Enabled only when VLLM_BASE_URL is set.

    Structured output uses ``response_format: json_schema`` (vLLM's guided
    decoding), and the result is validated again here: a malformed or
    truncated answer is a transient failure, so the gateway falls back to the
    hosted models. Text-only: image input also falls through to the next route.
    """

    name = 'vllm'

    def __init__(self, base_url: str, timeout: float, api_key: str | None = None,
                 transport: httpx.AsyncBaseTransport | None = None):
        headers = {'Authorization': f'Bearer {api_key}'} if api_key else {}
        # base_url follows the OpenAI convention and includes /v1, e.g. http://vllm:8000/v1
        self.client = httpx.AsyncClient(base_url=base_url.rstrip('/'), timeout=timeout, headers=headers,
                                        transport=transport, follow_redirects=False)

    async def structured(self, route: Route, system: str, user: UserContent, schema: type[T]) -> tuple[T, Usage]:
        if not isinstance(user, str):
            raise ProviderError('vLLM route is text-only')
        body = {
            'model': route.model,
            'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
            'max_tokens': route.max_tokens,
            'response_format': {'type': 'json_schema',
                                'json_schema': {'name': schema.__name__, 'schema': schema.model_json_schema()}},
        }
        try:
            resp = await self.client.post('/chat/completions', json=body)
        except httpx.HTTPError as exc:
            raise ProviderError(type(exc).__name__) from exc
        # 404: the adapter isn't loaded on this server; treat like an outage and fall back.
        if resp.status_code in (404, 408, 429) or resp.status_code >= 500:
            raise ProviderError(f'HTTP {resp.status_code}')
        if resp.status_code >= 400:
            raise ValueError(f'vLLM rejected the request (HTTP {resp.status_code})')
        try:
            data = resp.json()
            choice = data['choices'][0]
            content = choice['message']['content'] or ''
            u = data.get('usage') or {}
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError('Malformed response') from exc
        if choice.get('finish_reason') == 'length':
            raise ProviderError('Incomplete output (length)')
        try:
            parsed = schema.model_validate_json(content)
        except ValidationError as exc:
            raise ProviderError('Output did not match the schema') from exc
        cached = (u.get('prompt_tokens_details') or {}).get('cached_tokens') or 0
        return parsed, Usage(int(u.get('prompt_tokens') or 0), int(u.get('completion_tokens') or 0), int(cached))
