"""
Voice eval: latency waterfall, transcript error and barge-in for each engine.

    python -m evals.run_voice --engine realtime
    python -m evals.run_voice --engine cascaded     # needs DEEPGRAM_API_KEY

Test speech is synthesised, then streamed in real time as a microphone would
send it, followed by silence so the engine can detect the end of the turn. WER
on clean synthetic speech is a best case: it says nothing about South African
accents or code-switching, which need recordings of real people.

"Speech end to first audio" is what a member feels. Network and playback between
the browser and this service aren't included.
"""
import argparse
import asyncio
import json
import os
import statistics
import time
from pathlib import Path

from openai import OpenAI

from app.budget import Budget
from app.features import voice
from app.main import build_gateway

PHRASES = Path(__file__).parent / 'datasets' / 'voice_v1.jsonl'
FRAME = voice.BYTES_PER_SECOND // 50  # 20 ms
SILENCE_S = 4.0


def synthesise(client, text):
    with client.audio.speech.with_streaming_response.create(model='gpt-4o-mini-tts', voice='alloy', input=text,
                                                            response_format='pcm') as res:
        return b''.join(res.iter_bytes())


class Recorder:
    def __init__(self):
        self.events, self.first_audio_at = [], None

    async def send_json(self, data):
        self.events.append((time.monotonic(), data))

    async def send_bytes(self, data):
        if self.first_audio_at is None:
            self.first_audio_at = time.monotonic()

    def of(self, kind):
        return [d for _, d in self.events if d['type'] == kind]


async def stream(engine, pcm):
    for i in range(0, len(pcm), FRAME):
        await engine.audio(pcm[i:i + FRAME])
        await asyncio.sleep(0.02)


async def silence(engine, seconds, until=None):
    frame = b'\x00' * FRAME
    for _ in range(int(seconds * 50)):
        await engine.audio(frame)
        await asyncio.sleep(0.02)
        if until is not None and until():
            return


def make_engine(name, peer, gateway):
    return voice.build_engine(name, peer, gateway, 1, [], deepgram_key=os.environ.get('DEEPGRAM_API_KEY') or None,
                              openai_key=os.environ.get('OPENAI_API_KEY') or None)


async def measure(name, gateway, item, pcm):
    peer = Recorder()
    engine = make_engine(name, peer, gateway)
    await engine.start()
    await asyncio.sleep(0.3)
    await silence(engine, 0.5)
    await stream(engine, pcm)
    speech_end = time.monotonic()
    await silence(engine, SILENCE_S, until=lambda: peer.first_audio_at is not None)
    # Let the reply and its metrics finish.
    deadline = time.monotonic() + 15
    while not peer.of('turn_metrics') and not peer.of('error') and time.monotonic() < deadline:
        await silence(engine, 0.2)
    await engine.close()
    finals = [e['text'] for e in peer.of('transcript') if e.get('final')]
    stages = peer.of('turn_metrics')[0] if peer.of('turn_metrics') else {}
    return {
        'id': item['id'],
        'wer': voice.word_error_rate(item['text'], ' '.join(finals)) if finals else None,
        'speech_end_to_audio_ms': round((peer.first_audio_at - speech_end) * 1000) if peer.first_audio_at else None,
        'turn_end_to_token_ms': stages.get('llm_first_token'),
        'turn_end_to_audio_ms': stages.get('first_audio'),
        'cost_usd': stages.get('cost_usd', 0),
        'errors': [e['code'] for e in peer.of('error')],
    }


async def barge_in(name, gateway, pcm):
    """Interrupt a reply while it plays. Success: the engine signals an interrupt within 2 s of the new speech."""
    peer = Recorder()
    engine = make_engine(name, peer, gateway)
    await engine.start()
    await asyncio.sleep(0.3)
    await silence(engine, 0.5)
    await stream(engine, pcm)
    await silence(engine, 8, until=lambda: peer.first_audio_at is not None)
    if peer.first_audio_at is None:
        await engine.close()
        return None
    speaking_at = time.monotonic()
    await stream(engine, pcm)
    await silence(engine, 1, until=lambda: bool(peer.of('interrupt')))
    interrupted = [t for t, d in peer.events if d['type'] == 'interrupt']
    await engine.close()
    return round((interrupted[0] - speaking_at) * 1000) if interrupted else None


def p95(values):
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * 0.95))] if values else None


async def run(name, limit):
    items = [json.loads(line) for line in PHRASES.read_text(encoding='utf-8').splitlines() if line.strip()][:limit]
    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
    audio = {i['id']: synthesise(client, i['text']) for i in items}
    gateway, _ = build_gateway()
    gateway.budget = Budget(10_000_000, daily_audio_seconds=100_000)
    rows = [await measure(name, gateway, i, audio[i['id']]) for i in items]
    for row in rows:
        print(json.dumps(row))
    barge = [await barge_in(name, gateway, audio[i['id']]) for i in items[:5]]

    def column(key):
        return [r[key] for r in rows if r[key] is not None]

    wers = column('wer')
    print(f'\nEngine {name}, {len(rows)} turns (synthetic speech)')
    for label, key in (('Speech end to first audio', 'speech_end_to_audio_ms'),
                       ('Turn end to first token', 'turn_end_to_token_ms'),
                       ('Turn end to first audio', 'turn_end_to_audio_ms')):
        values = column(key)
        if values:
            print(f'{label}: p50 {statistics.median(values):.0f} ms, p95 {p95(values)} ms ({len(values)} turns)')
    if wers:
        print(f'Mean WER: {statistics.mean(wers):.3f} ({len(wers)} turns)')
    print(f"Barge-in: {sum(b is not None for b in barge)}/{len(barge)} detected, ms {[b for b in barge if b]}")
    print(f"Cost: ${sum(r['cost_usd'] for r in rows):.4f} for {len(rows)} turns")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--engine', choices=['cascaded', 'realtime'], default='realtime')
    ap.add_argument('--limit', type=int, default=10)
    a = ap.parse_args()
    asyncio.run(run(a.engine, a.limit))
