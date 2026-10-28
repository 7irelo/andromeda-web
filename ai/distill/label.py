"""
Step 2: label the corpus with the frontier model, using the production policy.

    python -m distill.label --in distill/data/corpus.jsonl --out distill/data/labels.jsonl

Uses Claude Opus 5.5 through the Message Batches API (half price; latency
doesn't matter offline). `--sync` labels with concurrent normal requests
instead, for quick small runs. Labels use exactly the policy text the
service runs (`app.features.moderation.POLICY`), so the student learns the
current policy.
"""
import argparse
import asyncio
import json
import os
import time
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

from app.features.moderation import POLICY, Verdict
from app.guardrails import untrusted

MODEL = 'claude-opus-5-5'
SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['decision', 'categories', 'confidence', 'reason'],
    'properties': {
        'decision': {'type': 'string', 'enum': ['allow', 'review', 'remove']},
        'categories': {'type': 'array', 'items': {'type': 'string', 'enum': [
            'none', 'spam', 'scam', 'harassment', 'hate', 'sexual', 'violence', 'self_harm', 'illegal_goods',
            'personal_data', 'other']}},
        'confidence': {'type': 'number'},
        'reason': {'type': 'string'},
    },
}


def _params(row):
    return MessageCreateParamsNonStreaming(
        model=MODEL, max_tokens=2000,
        system=[{'type': 'text', 'text': POLICY, 'cache_control': {'type': 'ephemeral'}}],
        messages=[{'role': 'user', 'content': untrusted(row['text'], 10_000, kind=row['content_type'])}],
        output_config={'effort': 'low', 'format': {'type': 'json_schema', 'schema': SCHEMA}},
    )


def _text(message):
    return next((b.text for b in message.content if b.type == 'text'), '')


def label_batch(rows):
    client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
    batch = client.messages.batches.create(requests=[Request(custom_id=r['id'], params=_params(r)) for r in rows])
    print(f'Batch {batch.id} submitted ({len(rows)} requests)')
    while True:
        batch = client.messages.batches.retrieve(batch.id)
        if batch.processing_status == 'ended':
            break
        print(f'  {batch.request_counts.processing} processing...')
        time.sleep(30)
    labels, usage = {}, [0, 0]
    for result in client.messages.batches.results(batch.id):
        if result.result.type != 'succeeded':
            continue
        msg = result.result.message
        try:
            labels[result.custom_id] = Verdict.model_validate_json(_text(msg))
        except ValueError:
            continue
        usage[0] += msg.usage.input_tokens + (msg.usage.cache_read_input_tokens or 0)
        usage[1] += msg.usage.output_tokens
    return labels, usage, 0.5  # batch discount


async def _one(client, row, sem):
    async with sem:
        msg = await client.messages.create(**_params(row))
        return row['id'], msg


def label_sync(rows):
    async def run():
        client = anthropic.AsyncAnthropic(api_key=os.environ['ANTHROPIC_API_KEY'], max_retries=3)
        sem = asyncio.Semaphore(8)
        return await asyncio.gather(*(_one(client, r, sem) for r in rows), return_exceptions=True)
    labels, usage = {}, [0, 0]
    for res in asyncio.run(run()):
        if isinstance(res, Exception):
            continue
        rid, msg = res
        try:
            labels[rid] = Verdict.model_validate_json(_text(msg))
        except ValueError:
            continue
        usage[0] += msg.usage.input_tokens + (msg.usage.cache_read_input_tokens or 0)
        usage[1] += msg.usage.output_tokens
    return labels, usage, 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='src', type=Path, default=Path(__file__).parent / 'data' / 'corpus.jsonl')
    ap.add_argument('--out', type=Path, default=Path(__file__).parent / 'data' / 'labels.jsonl')
    ap.add_argument('--sync', action='store_true')
    a = ap.parse_args()
    rows = [json.loads(line) for line in a.src.read_text(encoding='utf-8').splitlines() if line.strip()]
    labels, (tin, tout), discount = (label_sync if a.sync else label_batch)(rows)
    with a.out.open('w', encoding='utf-8') as f:
        for r in rows:
            v = labels.get(r['id'])
            if v is not None:
                f.write(json.dumps({**r, 'label': v.decision, 'categories': v.categories,
                                    'teacher_confidence': v.confidence, 'teacher': MODEL}, ensure_ascii=False) + '\n')
    cost = (tin * 4.0 + tout * 20.0) / 1e6 * discount
    print(f'{len(labels)}/{len(rows)} labelled -> {a.out}; {tin} in / {tout} out tokens, ~${cost:.2f}')


if __name__ == '__main__':
    main()
