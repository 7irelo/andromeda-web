"""
Realtime voice: talk to the Assistant, with two interchangeable engines.

    cascaded   Deepgram Flux -> Claude (streaming) -> Deepgram Aura-2
    realtime   OpenAI speech-to-speech (gpt-realtime-2.1-mini)

The browser never talks to a provider. Audio goes browser -> Django -> here, so
keys stay in this service and Django has already checked who is connected.

Both engines use one protocol with their peer (Django):

    binary     PCM16 mono, 24 kHz, in both directions
    in JSON    {"type": "tool_result", "call_id", "content", "is_error"}
    out JSON   ready | transcript {text, final} | reply {text} | interrupt
               tool_call {id, name, arguments} | turn_metrics {...} | error {code}

Tools run in Django as the member, and voice only gets the read tools: writing
needs a confirmation card, so spoken requests to post are sent to the panel.
Barge-in: when the member starts talking during a reply, the reply and its
queued audio are cancelled and the peer is told to drop what it has buffered.
"""
import asyncio
import base64
import json
import logging
import re
import time
from typing import Protocol
from urllib.parse import urlencode

import websockets
from prometheus_client import Counter, Histogram

from .. import metrics
from ..gateway import AllRoutesFailed, BudgetExceeded, Gateway, ProviderError, Refused, Turn
from ..guardrails import UNTRUSTED_NOTICE, clean_text, strip_foreign_urls, untrusted

logger = logging.getLogger(__name__)

SAMPLE_RATE = 24000
BYTES_PER_SECOND = SAMPLE_RATE * 2
MAX_SESSION_SECONDS = 600
MAX_TOOL_ROUNDS = 3
MAX_TURNS_KEPT = 20
TOOL_TIMEOUT_S = 8.0
TOOL_RESULT_CHARS = 4000

FLUX_URL = 'wss://api.deepgram.com/v2/listen'
AURA_URL = 'wss://api.deepgram.com/v1/speak'
TTS_MODEL = 'aura-2-thalia-en'
REALTIME_URL = 'wss://api.openai.com/v1/realtime'
REALTIME_MODEL = 'gpt-realtime-2.1-mini'
REALTIME_TRANSCRIBE_MODEL = 'gpt-4o-mini-transcribe'
REALTIME_PRICE = (10.00, 20.00)  # USD per 1M audio tokens, input and output
EOT_THRESHOLD = 0.7

STAGE = Histogram('ai_voice_stage_seconds', 'Time from the end of the turn to each stage', ['engine', 'stage'],
                  buckets=(0.1, 0.2, 0.3, 0.5, 0.8, 1.2, 2, 4, 8))
BARGE_INS = Counter('ai_voice_barge_ins_total', 'Replies interrupted by the member', ['engine'])
SESSIONS = Counter('ai_voice_sessions_total', 'Voice sessions', ['engine', 'outcome'])

SYSTEM = f"""You are Andromeda's voice assistant on a social network. Your words are spoken aloud.
{UNTRUSTED_NOTICE}

- Keep replies to one or two short sentences. No lists, markdown or links, and don't spell out URLs.
- Use the tools to look things up. They return only what this member may see. Don't state facts about
  people or posts that you didn't get from a tool, and say so when you can't find something.
- You can't post or send messages by voice. If asked, say they can do that from the assistant panel, where
  they'll see exactly what will be sent.
- The member's words come from speech recognition, so read past small transcription errors."""

_SENTENCE_END = re.compile(r'(?<=[.!?])\s')


class Peer(Protocol):
    async def send_json(self, data: dict) -> None: ...

    async def send_bytes(self, data: bytes) -> None: ...


class VoiceUnavailable(Exception):
    pass


def split_sentences(buffer: str) -> tuple[list[str], str]:
    """Complete sentences, and whatever is left over. Sending whole sentences keeps speech natural."""
    parts = _SENTENCE_END.split(buffer)
    return [p.strip() for p in parts[:-1] if p.strip()], parts[-1]


def word_error_rate(reference: str, hypothesis: str) -> float:
    def words(text):
        return re.sub(r"[^\w\s']", '', text.casefold()).split()

    ref, hyp = words(reference), words(hypothesis)
    if not ref:
        return float(bool(hyp))
    row = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, row[0] = row[0], i
        for j, h in enumerate(hyp, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (r != h))
    return row[-1] / len(ref)


class Engine:
    name = ''

    def __init__(self, peer: Peer, gateway: Gateway, user_id: int, tools: list[dict]):
        self.peer = peer
        self.gateway = gateway
        self.user_id = user_id
        self.tools = tools
        self.audio_bytes = 0
        self.turn_ended_at: float | None = None
        self._tool_waiters: dict[str, asyncio.Future] = {}
        self._tasks: list[asyncio.Task] = []

    @property
    def audio_seconds(self) -> float:
        return self.audio_bytes / BYTES_PER_SECOND

    def tool_result(self, call_id: str, content: str, is_error: bool) -> None:
        waiter = self._tool_waiters.get(call_id)
        if waiter is not None and not waiter.done():
            waiter.set_result((str(content)[:TOOL_RESULT_CHARS], bool(is_error)))

    async def _call_tool(self, call_id: str, name: str, arguments: dict) -> tuple[str, bool]:
        waiter = asyncio.get_running_loop().create_future()
        self._tool_waiters[call_id] = waiter
        await self.peer.send_json({'type': 'tool_call', 'id': call_id, 'name': name, 'arguments': arguments})
        try:
            content, is_error = await asyncio.wait_for(waiter, TOOL_TIMEOUT_S)
        except TimeoutError:
            return 'That lookup took too long.', True
        finally:
            self._tool_waiters.pop(call_id, None)
        return untrusted(content, TOOL_RESULT_CHARS, kind='tool_result', tool=name), is_error

    def _mark(self, stages: dict, stage: str) -> None:
        if stage not in stages and self.turn_ended_at is not None:
            elapsed = time.monotonic() - self.turn_ended_at
            stages[stage] = round(elapsed * 1000)
            STAGE.labels(self.name, stage).observe(elapsed)

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)


class CascadedEngine(Engine):
    """Flux decides when a turn ends, which replaces hand-tuned VAD and endpointing."""

    name = 'cascaded'

    def __init__(self, peer, gateway, user_id, tools, api_key: str, connect=websockets.connect):
        super().__init__(peer, gateway, user_id, tools)
        self.api_key = api_key
        self.connect = connect
        self.stt = None
        self.tts = None
        self.turns: list[Turn] = []
        self.reply_task: asyncio.Task | None = None
        self.stages: dict = {}
        self.sources = ''

    def _headers(self) -> dict:
        return {'Authorization': f'Token {self.api_key}'}

    async def _open_tts(self):
        query = urlencode({'model': TTS_MODEL, 'encoding': 'linear16', 'sample_rate': SAMPLE_RATE,
                           'mip_opt_out': 'true'})
        self.tts = await self.connect(f'{AURA_URL}?{query}', additional_headers=self._headers())
        self._tasks.append(asyncio.create_task(self._read_tts(self.tts)))

    async def start(self) -> None:
        query = urlencode({'model': 'flux-general-en', 'encoding': 'linear16', 'sample_rate': SAMPLE_RATE,
                           'eot_threshold': EOT_THRESHOLD, 'mip_opt_out': 'true'})
        try:
            self.stt = await self.connect(f'{FLUX_URL}?{query}', additional_headers=self._headers())
            await self._open_tts()
        except (OSError, websockets.WebSocketException) as exc:
            raise VoiceUnavailable(type(exc).__name__) from exc
        self._tasks.append(asyncio.create_task(self._read_stt()))
        await self.peer.send_json({'type': 'ready'})

    async def audio(self, chunk: bytes) -> None:
        self.audio_bytes += len(chunk)
        await self.stt.send(chunk)

    async def _read_stt(self) -> None:
        try:
            async for raw in self.stt:
                if isinstance(raw, str):
                    await self.on_stt(json.loads(raw))
        except websockets.WebSocketException:
            await self.peer.send_json({'type': 'error', 'code': 'stt_lost'})

    async def on_stt(self, msg: dict) -> None:
        if msg.get('type') != 'TurnInfo':
            return
        event, text = msg.get('event'), msg.get('transcript') or ''
        if event == 'StartOfTurn':
            await self._barge_in()
        if event in ('StartOfTurn', 'Update') and text:
            await self.peer.send_json({'type': 'transcript', 'text': text, 'final': False})
        elif event == 'EndOfTurn' and text.strip():
            self.turn_ended_at = time.monotonic()
            await self.peer.send_json({'type': 'transcript', 'text': text, 'final': True})
            await self._barge_in()
            self.reply_task = asyncio.create_task(self._reply(text))

    async def _barge_in(self) -> None:
        if self.reply_task is None or self.reply_task.done():
            return
        self.reply_task.cancel()
        await asyncio.gather(self.reply_task, return_exceptions=True)
        BARGE_INS.labels(self.name).inc()
        await self.peer.send_json({'type': 'interrupt'})
        await self._send_tts({'type': 'Clear'})

    async def _send_tts(self, message: dict) -> None:
        """Aura drops idle connections, so reopen once if this one has gone."""
        for attempt in (1, 2):
            try:
                await self.tts.send(json.dumps(message))
                return
            except websockets.ConnectionClosed:
                if attempt == 2:
                    raise
                await self._open_tts()

    async def _read_tts(self, connection) -> None:
        try:
            async for raw in connection:
                if isinstance(raw, bytes):
                    self._mark(self.stages, 'first_audio')
                    await self.peer.send_bytes(raw)
        except websockets.ConnectionClosed:
            pass

    async def _speak(self, sentence: str) -> None:
        sentence = strip_foreign_urls(sentence, self.sources)
        await self.peer.send_json({'type': 'reply', 'text': sentence})
        await self._send_tts({'type': 'Speak', 'text': sentence})
        await self._send_tts({'type': 'Flush'})

    async def _reply(self, text: str) -> None:
        self.stages = {}
        self.turns.append({'role': 'user', 'text': clean_text(text, 2000)})
        self.turns = self.turns[-MAX_TURNS_KEPT:]
        while self.turns and self.turns[0]['role'] != 'user':  # never start a conversation mid-tool-call
            self.turns.pop(0)
        spoken: list[str] = []
        buffer = ''

        async def on_text(delta: str) -> None:
            nonlocal buffer
            self._mark(self.stages, 'llm_first_token')
            sentences, buffer = split_sentences(buffer + delta)
            for sentence in sentences:
                spoken.append(sentence)
                await self._speak(sentence)

        try:
            for _ in range(MAX_TOOL_ROUNDS):
                result = await self.gateway.stream_step('voice.reply', system=SYSTEM, turns=self.turns,
                                                        tools=self.tools, user_id=self.user_id, on_text=on_text)
                output = result.output
                if not output.tool_calls:
                    break
                self.turns.append({'role': 'assistant', 'text': output.text, 'native': output.native,
                                   'tool_calls': [{'id': c.id, 'name': c.name, 'arguments': c.arguments}
                                                  for c in output.tool_calls]})
                results = []
                for call in output.tool_calls:
                    content, is_error = await self._call_tool(call.id, call.name, call.arguments)
                    self.sources += content
                    results.append({'call_id': call.id, 'name': call.name, 'content': content, 'is_error': is_error})
                self.turns.append({'role': 'tool', 'results': results})
            if buffer.strip():
                spoken.append(buffer.strip())
                await self._speak(buffer.strip())
                buffer = ''
            self.turns.append({'role': 'assistant', 'text': ' '.join(spoken) or '(no reply)'})
            await self.peer.send_json({'type': 'turn_metrics', 'engine': self.name, **self.stages})
        except asyncio.CancelledError:
            # Keep the history valid, and record only what the member actually heard.
            if self.turns[-1]['role'] == 'tool' or (self.turns[-1]['role'] == 'assistant'
                                                    and self.turns[-1].get('tool_calls')):
                self.turns = [t for t in self.turns if t['role'] != 'tool' and not t.get('tool_calls')]
            self.turns.append({'role': 'assistant', 'text': ' '.join(spoken) or '(interrupted)'})
            raise
        except (AllRoutesFailed, ProviderError, Refused, BudgetExceeded) as exc:
            logger.warning('Voice reply failed: %s', type(exc).__name__)
            self.turns.append({'role': 'assistant', 'text': '(no reply)'})
            await self.peer.send_json({'type': 'error', 'code': 'reply_failed'})

    async def close(self) -> None:
        if self.reply_task is not None:
            self.reply_task.cancel()
            await asyncio.gather(self.reply_task, return_exceptions=True)
        for connection, message in ((self.stt, {'type': 'CloseStream'}), (self.tts, {'type': 'Close'})):
            if connection is not None:
                try:
                    await connection.send(json.dumps(message))
                    await connection.close()
                except websockets.WebSocketException:
                    pass
        await super().close()


class RealtimeEngine(Engine):
    """OpenAI's speech-to-speech model: it handles turn detection, the reply and the voice itself."""

    name = 'realtime'

    def __init__(self, peer, gateway, user_id, tools, api_key: str, model: str = REALTIME_MODEL,
                 connect=websockets.connect):
        super().__init__(peer, gateway, user_id, tools)
        self.api_key = api_key
        self.model = model
        self.connect = connect
        self.ws = None
        self.responding = False
        self.stages: dict = {}
        self.cost_usd = 0.0

    async def start(self) -> None:
        try:
            self.ws = await self.connect(f"{REALTIME_URL}?{urlencode({'model': self.model})}",
                                         additional_headers={'Authorization': f'Bearer {self.api_key}'},
                                         max_size=8 * 1024 * 1024)
        except (OSError, websockets.WebSocketException) as exc:
            raise VoiceUnavailable(type(exc).__name__) from exc
        pcm = {'type': 'audio/pcm', 'rate': SAMPLE_RATE}
        await self._send({'type': 'session.update', 'session': {
            'type': 'realtime',
            'output_modalities': ['audio'],
            'instructions': SYSTEM,
            'audio': {
                'input': {'format': pcm, 'turn_detection': {'type': 'semantic_vad'},
                          'transcription': {'model': REALTIME_TRANSCRIBE_MODEL}},
                'output': {'format': pcm, 'voice': 'marin'},
            },
            'tools': [{'type': 'function', 'name': t['name'], 'description': t['description'],
                       'parameters': t['input_schema']} for t in self.tools],
            'tool_choice': 'auto',
        }})
        self._tasks.append(asyncio.create_task(self._read()))
        await self.peer.send_json({'type': 'ready'})

    async def _send(self, event: dict) -> None:
        await self.ws.send(json.dumps(event))

    async def audio(self, chunk: bytes) -> None:
        self.audio_bytes += len(chunk)
        await self._send({'type': 'input_audio_buffer.append', 'audio': base64.b64encode(chunk).decode()})

    async def _read(self) -> None:
        try:
            async for raw in self.ws:
                await self.on_event(json.loads(raw))
        except websockets.WebSocketException:
            await self.peer.send_json({'type': 'error', 'code': 'stream_lost'})

    async def on_event(self, event: dict) -> None:
        kind = event.get('type')
        if kind == 'input_audio_buffer.speech_started':
            if self.responding:  # semantic VAD cancels the response itself; the peer still has audio buffered
                self.responding = False
                BARGE_INS.labels(self.name).inc()
                await self.peer.send_json({'type': 'interrupt'})
        elif kind == 'input_audio_buffer.speech_stopped':
            self.turn_ended_at = time.monotonic()
            self.stages = {}
        elif kind == 'response.created':
            self.responding = True
        elif kind == 'conversation.item.input_audio_transcription.completed':
            await self.peer.send_json({'type': 'transcript', 'text': event.get('transcript', ''), 'final': True})
        elif kind == 'response.output_audio_transcript.delta':
            self._mark(self.stages, 'llm_first_token')
            await self.peer.send_json({'type': 'reply', 'text': event.get('delta', '')})
        elif kind == 'response.output_audio.delta':
            self._mark(self.stages, 'first_audio')
            await self.peer.send_bytes(base64.b64decode(event.get('delta', '')))
        elif kind == 'response.done':
            await self._response_done(event.get('response') or {})
        elif kind == 'error':
            error = event.get('error') or {}
            logger.warning('Realtime error: %s', error.get('code') or error.get('type'))
            if error.get('code') != 'response_cancel_not_active':
                await self.peer.send_json({'type': 'error', 'code': 'provider_error'})

    async def _response_done(self, response: dict) -> None:
        self.responding = False
        usage = response.get('usage') or {}
        tokens_in, tokens_out = usage.get('input_tokens', 0), usage.get('output_tokens', 0)
        cost = (tokens_in * REALTIME_PRICE[0] + tokens_out * REALTIME_PRICE[1]) / 1_000_000
        self.cost_usd += cost
        self.gateway.budget.spend(self.user_id, tokens_in + tokens_out)
        metrics.COST.labels('voice.reply', self.model).inc(cost)
        metrics.TOKENS.labels('voice.reply', self.model, 'input').inc(tokens_in)
        metrics.TOKENS.labels('voice.reply', self.model, 'output').inc(tokens_out)
        calls = [o for o in response.get('output') or [] if o.get('type') == 'function_call']
        for call in calls:
            try:
                arguments = json.loads(call.get('arguments') or '{}')
            except json.JSONDecodeError:
                arguments = {}
            content, _ = await self._call_tool(call['call_id'], call['name'], arguments)
            await self._send({'type': 'conversation.item.create',
                              'item': {'type': 'function_call_output', 'call_id': call['call_id'], 'output': content}})
        if calls:
            await self._send({'type': 'response.create'})
        elif response.get('status') == 'completed':
            await self.peer.send_json({'type': 'turn_metrics', 'engine': self.name, 'cost_usd': round(cost, 5),
                                       **self.stages})

    async def close(self) -> None:
        if self.ws is not None:
            try:
                await self.ws.close()
            except websockets.WebSocketException:
                pass
        await super().close()


def build_engine(name: str, peer: Peer, gateway: Gateway, user_id: int, tools: list[dict], *,
                 deepgram_key: str | None, openai_key: str | None) -> Engine:
    if name == 'cascaded' and deepgram_key:
        return CascadedEngine(peer, gateway, user_id, tools, deepgram_key)
    if name == 'realtime' and openai_key:
        return RealtimeEngine(peer, gateway, user_id, tools, openai_key)
    raise VoiceUnavailable(f'{name} is not configured')


async def run_session(engine: Engine, receive, budget) -> str:
    """Pump the peer's messages into the engine until it leaves, the time limit hits or the allowance runs out."""
    started = time.monotonic()
    billed = 0.0
    outcome = 'closed'
    try:
        await engine.start()
        while True:
            remaining = MAX_SESSION_SECONDS - (time.monotonic() - started)
            if remaining <= 0:
                outcome = 'time_limit'
                break
            try:
                message = await asyncio.wait_for(receive(), remaining)
            except TimeoutError:
                outcome = 'time_limit'
                break
            if message is None:
                break
            if isinstance(message, bytes):
                await engine.audio(message)
                if engine.audio_seconds - billed >= 10:
                    budget.spend_audio(engine.user_id, engine.audio_seconds - billed)
                    billed = engine.audio_seconds
                    if not budget.has_audio_room(engine.user_id):
                        outcome = 'budget'
                        break
            elif message.get('type') == 'tool_result':
                engine.tool_result(str(message.get('call_id')), message.get('content') or '',
                                   bool(message.get('is_error')))
    except VoiceUnavailable:
        outcome = 'unavailable'
    except websockets.WebSocketException:
        outcome = 'provider_lost'
    finally:
        if engine.audio_seconds > billed:
            budget.spend_audio(engine.user_id, engine.audio_seconds - billed)
        await engine.close()
        SESSIONS.labels(engine.name, outcome).inc()
    return outcome
