"""
Speech: Deepgram for every audio leg.

- Pre-recorded transcription (voice notes, video captions) uses Nova-3 with
  smart formatting and language detection; video adds diarization,
  utterances and paragraphs so captions and chapters get speaker turns and
  timestamps.
- Text-to-speech uses Aura-2.

Audio arrives from Django, never from a browser, and every request sets
`mip_opt_out=true` so it's excluded from Deepgram's model-improvement
programme. Usage is metered per user in audio seconds.
"""
import base64
import binascii
import logging
import time
from typing import Literal

import httpx
from fastapi import HTTPException, status
from prometheus_client import Counter, Histogram
from pydantic import BaseModel, Field

from ..budget import Budget

logger = logging.getLogger(__name__)

DEEPGRAM_URL = 'https://api.deepgram.com/v1'
STT_MODEL = 'nova-3'
TTS_MODEL = 'aura-2-thalia-en'
MAX_AUDIO_BYTES = 25 * 1024 * 1024
ALLOWED_AUDIO = {'audio/webm', 'audio/ogg', 'audio/mpeg', 'audio/mp4', 'audio/wav', 'audio/x-wav', 'audio/aac',
                 'audio/flac'}
PRICE_PER_MINUTE = {'nova-3': 0.0043, 'aura-2': 0.030 / 1000}  # STT per audio minute; TTS per character

AUDIO_SECONDS = Counter('ai_audio_seconds_total', 'Audio transcribed', ['purpose', 'model'])
SPEECH_LATENCY = Histogram('ai_speech_latency_seconds', 'Deepgram call latency', ['op'],
                           buckets=(0.25, 0.5, 1, 2, 4, 8, 16, 32, 64))
SPEECH_ERRORS = Counter('ai_speech_errors_total', 'Deepgram failures', ['op'])


class Utterance(BaseModel):
    start: float
    end: float
    speaker: int | None = None
    text: str


class TranscribeRequest(BaseModel):
    audio_b64: str = Field(max_length=MAX_AUDIO_BYTES * 4 // 3 + 16)
    mimetype: str = Field(max_length=40)
    purpose: Literal['voice_note', 'video'] = 'voice_note'


class TranscribeResult(BaseModel):
    transcript: str
    language: str | None
    duration_s: float
    utterances: list[Utterance]
    paragraphs: list[str]
    vtt: str | None = None
    model: str
    cost_usd: float


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class SpeechUnavailable(Exception):
    pass


class DeepgramClient:
    def __init__(self, api_key: str, timeout: float = 60.0):
        self._client = httpx.AsyncClient(base_url=DEEPGRAM_URL, timeout=timeout,
                                         headers={'Authorization': f'Token {api_key}'})

    async def listen(self, audio: bytes, mimetype: str, video: bool) -> dict:
        params = {'model': STT_MODEL, 'smart_format': 'true', 'detect_language': 'true', 'punctuate': 'true',
                  'mip_opt_out': 'true'}
        if video:
            params.update({'diarize': 'true', 'utterances': 'true', 'paragraphs': 'true'})
        try:
            r = await self._client.post('/listen', params=params, content=audio, headers={'Content-Type': mimetype})
        except httpx.HTTPError as exc:
            raise SpeechUnavailable(type(exc).__name__) from exc
        if r.status_code >= 500 or r.status_code == 429:
            raise SpeechUnavailable(f'HTTP {r.status_code}')
        if r.status_code >= 400:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, 'The audio could not be transcribed')
        return r.json()

    async def speak(self, text: str) -> bytes:
        try:
            r = await self._client.post('/speak', params={'model': TTS_MODEL, 'encoding': 'mp3', 'mip_opt_out': 'true'},
                                        json={'text': text})
        except httpx.HTTPError as exc:
            raise SpeechUnavailable(type(exc).__name__) from exc
        if r.status_code >= 400:
            raise SpeechUnavailable(f'HTTP {r.status_code}')
        return r.content


def parse_listen(data: dict) -> tuple[str, str | None, float, list[Utterance], list[str]]:
    results = data.get('results') or {}
    channel = (results.get('channels') or [{}])[0]
    alt = (channel.get('alternatives') or [{}])[0]
    transcript = (alt.get('paragraphs') or {}).get('transcript') or alt.get('transcript') or ''
    paragraphs = []
    for p in (alt.get('paragraphs') or {}).get('paragraphs') or []:
        text = ' '.join(s.get('text', '') for s in p.get('sentences') or []).strip()
        if text:
            paragraphs.append(text)
    utterances = [Utterance(start=u.get('start', 0.0), end=u.get('end', 0.0), speaker=u.get('speaker'),
                            text=u.get('transcript', '')) for u in results.get('utterances') or []]
    duration = float((data.get('metadata') or {}).get('duration') or 0.0)
    return transcript.strip(), channel.get('detected_language'), duration, utterances, paragraphs


def decode_audio(req: TranscribeRequest) -> bytes:
    mimetype = req.mimetype.split(';')[0].strip().lower()
    if mimetype not in ALLOWED_AUDIO:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, 'Unsupported audio type')
    try:
        audio = base64.b64decode(req.audio_b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, 'Audio is not valid base64') from None
    if not audio or len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, 'Audio is empty or too large')
    return audio


async def transcribe(req: TranscribeRequest, client: DeepgramClient | None, budget: Budget,
                     user_id: int) -> TranscribeResult:
    if client is None:
        raise SpeechUnavailable('Speech is not configured')
    audio = decode_audio(req)
    if not budget.has_audio_room(user_id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, 'Daily audio allowance used up')
    started = time.monotonic()
    try:
        data = await client.listen(audio, req.mimetype.split(';')[0].strip().lower(), video=req.purpose == 'video')
    except SpeechUnavailable:
        SPEECH_ERRORS.labels('listen').inc()
        raise
    SPEECH_LATENCY.labels('listen').observe(time.monotonic() - started)
    transcript, language, duration, utterances, paragraphs = parse_listen(data)
    budget.spend_audio(user_id, duration)
    AUDIO_SECONDS.labels(req.purpose, STT_MODEL).inc(duration)
    vtt = to_webvtt(utterances) if req.purpose == 'video' and utterances else None
    return TranscribeResult(transcript=transcript, language=language, duration_s=duration, utterances=utterances,
                            paragraphs=paragraphs, vtt=vtt, model=STT_MODEL,
                            cost_usd=round(duration / 60 * PRICE_PER_MINUTE['nova-3'], 6))


def to_webvtt(utterances: list[Utterance], max_chars: int = 84) -> str:
    """WebVTT captions from timed utterances, split so cues stay readable."""
    def ts(t: float) -> str:
        h, rem = divmod(max(t, 0.0), 3600)
        m, s = divmod(rem, 60)
        return f'{int(h):02d}:{int(m):02d}:{s:06.3f}'

    lines = ['WEBVTT', '']
    for u in utterances:
        words = u.text.split()
        if not words:
            continue
        chunks, cur = [], ''
        for w in words:
            if len(cur) + len(w) + 1 > max_chars and cur:
                chunks.append(cur)
                cur = w
            else:
                cur = f'{cur} {w}'.strip()
        chunks.append(cur)
        span = (u.end - u.start) / len(chunks)
        for i, text in enumerate(chunks):
            start = u.start + i * span
            prefix = f'<v Speaker {u.speaker + 1}>' if u.speaker is not None else ''
            lines += [f'{ts(start)} --> {ts(start + span)}', f'{prefix}{text}', '']
    return '\n'.join(lines)
