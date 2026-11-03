"""
Realtime voice: a WebSocket relay between the browser and the AI service.

Django checks who is connecting, then relays audio both ways. Tool calls stop
here: they run as the connected member through the same ``tools.execute`` as the
assistant, limited to read tools, so voice can look things up but never write.
"""
import asyncio
import json
import logging

import websockets
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from django.core.cache import cache

from core import ai_client

from . import tools
from .models import PersonalAccessToken

logger = logging.getLogger(__name__)

MAX_FRAME_BYTES = 32 * 1024
MAX_AUDIO_BYTES_PER_SECOND = 96 * 1024  # twice real time (24 kHz PCM16), so a client can't flood the relay
SESSION_LOCK_SECONDS = 660
ENGINES = {'cascaded', 'realtime'}

CLOSE_UNAUTHORIZED = 4401
CLOSE_OPTED_OUT = 4403
CLOSE_BUSY = 4409
CLOSE_UNAVAILABLE = 4503

READ_SCOPES = (PersonalAccessToken.SCOPE_READ,)


def ai_voice_url(engine):
    base = settings.AI_SERVICE_URL.rstrip('/').replace('https://', 'wss://').replace('http://', 'ws://')
    return f'{base}/v1/voice?engine={engine}'


class VoiceConsumer(AsyncWebsocketConsumer):
    upstream = None
    relay_task = None
    lock_key = None

    async def connect(self):
        user = self.scope.get('user')
        if user is None or not user.is_authenticated:
            await self.close(code=CLOSE_UNAUTHORIZED)
            return
        if user.ai_opt_out or not ai_client.enabled():
            await self.close(code=CLOSE_OPTED_OUT if user.ai_opt_out else CLOSE_UNAVAILABLE)
            return
        self.lock_key = f'voice:session:{user.id}'
        if not cache.add(self.lock_key, 1, SESSION_LOCK_SECONDS):  # one conversation at a time per member
            self.lock_key = None
            await self.close(code=CLOSE_BUSY)
            return
        self.window_started = asyncio.get_running_loop().time()
        self.window_bytes = 0
        engine = getattr(settings, 'VOICE_ENGINE', 'cascaded')
        if engine not in ENGINES:
            engine = 'cascaded'
        try:
            self.upstream = await websockets.connect(
                ai_voice_url(engine),
                additional_headers={'Authorization': f'Bearer {ai_client._token(user.id)}'},
                max_size=MAX_FRAME_BYTES * 8,
            )
            await self.upstream.send(json.dumps({'tools': tools.specs(READ_SCOPES)}))
        except (OSError, websockets.WebSocketException) as exc:
            logger.warning('Voice relay could not reach the AI service: %s', type(exc).__name__)
            await self.close(code=CLOSE_UNAVAILABLE)
            return
        await self.accept()
        self.relay_task = asyncio.create_task(self._relay())

    async def receive(self, text_data=None, bytes_data=None):
        if bytes_data is None or self.upstream is None:  # the browser only ever sends audio
            return
        if len(bytes_data) > MAX_FRAME_BYTES or not self._within_rate(len(bytes_data)):
            return
        try:
            await self.upstream.send(bytes_data)
        except websockets.WebSocketException:
            await self.close(code=CLOSE_UNAVAILABLE)

    def _within_rate(self, size):
        now = asyncio.get_running_loop().time()
        if now - self.window_started >= 1:
            self.window_started, self.window_bytes = now, 0
        self.window_bytes += size
        return self.window_bytes <= MAX_AUDIO_BYTES_PER_SECOND

    async def _relay(self):
        try:
            async for message in self.upstream:
                if isinstance(message, bytes):
                    await self.send(bytes_data=message)
                else:
                    await self._from_ai(json.loads(message))
        except websockets.WebSocketException:
            pass
        # Pass on why the AI service ended the session (time limit, allowance, not configured).
        await self.close(code=self.upstream.close_code or CLOSE_UNAVAILABLE)

    async def _from_ai(self, event):
        if event.get('type') == 'tool_call':
            # Not awaited: a slow lookup mustn't hold up audio or an interruption.
            asyncio.create_task(self._run_tool(event))
            return
        await self.send(text_data=json.dumps(event))

    async def _run_tool(self, event):
        outcome = await self._execute(event.get('name'), event.get('arguments'))
        try:
            await self.upstream.send(json.dumps({'type': 'tool_result', 'call_id': event.get('id'),
                                                 'content': outcome.content, 'is_error': outcome.is_error}))
        except websockets.WebSocketException:
            pass

    @database_sync_to_async
    def _execute(self, name, arguments):
        ctx = tools.Context(user=self.scope['user'], scopes=READ_SCOPES)
        return tools.execute(name, arguments, ctx)

    async def disconnect(self, code):
        if self.relay_task is not None:
            self.relay_task.cancel()
        if self.upstream is not None:
            await self.upstream.close()
        if self.lock_key:
            cache.delete(self.lock_key)
