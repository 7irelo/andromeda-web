"""
Step 1: synthesise a training corpus for the distilled moderation classifier.

    python -m distill.generate --per-cell 8 --out distill/data/corpus.jsonl

Claude Sonnet writes short, realistic posts, comments and listings for every
(intent x language) cell, including hard negatives. The text is synthetic and
labelled as such; the *labels* come from step 2, not from the intent used to
prompt generation, so generation bias doesn't leak into training labels.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path

import anthropic
from pydantic import BaseModel, Field

INTENTS = {
    'clean': 'ordinary friendly posts, questions, event announcements, everyday buying and selling',
    'hard_negative': 'harmless text that looks risky to a keyword filter: sports trash talk, figures of speech '
                     '("that exam killed me"), news headlines about crime, profanity not aimed at anyone, helplines, '
                     'peaceful protest announcements, strong but civil disagreement',
    'borderline': 'content a human moderator should look at: veiled or conditional threats, put-downs without slurs, '
                  'blaming a group for social problems, hopelessness or goodbye messages, listings with fraud signals '
                  '(price too good, pay first, refuses to meet), prescription medicines for sale, asking where a '
                  'named person lives, spammy self-promotion',
    'violating': 'clear violations: scams with links or deposits, weapons or drugs for sale, credible threats, '
                 'hate speech with slurs replaced by [slur], doxxing with obviously fake ID numbers and addresses',
}
LANGS = {'en': 'South African English', 'zu': 'isiZulu', 'af': 'Afrikaans', 'mix': 'a mix of English and isiZulu or '
                                                                                  'Sesotho, as people really write'}


class Item(BaseModel):
    content_type: str = Field(description='post, comment or listing')
    text: str = Field(description='The content, 1-3 sentences, no hashtags spam, no real people or real phone numbers.')


class Batch(BaseModel):
    items: list[Item]


SYSTEM = ('You write synthetic test content for a South African social network\'s safety team. Content is fictional: '
          'never use real people\'s names with real details, real phone numbers, real ID numbers or real URLs '
          '(use example.test domains). Vary tone, length, slang and spelling like real users do.')


async def cell(client, intent, desc, lang, lang_desc, n, sem):
    async with sem:
        msg = await client.messages.parse(
            model='claude-sonnet-5-5', max_tokens=12000, system=SYSTEM, output_format=Batch,
            output_config={'effort': 'low'},
            messages=[{'role': 'user', 'content': f'Write {n} distinct items in {lang_desc}. Kind: {desc}.'}],
        )
        items = msg.parsed_output.items if msg.parsed_output else []
        return [{'text': i.text.strip(), 'content_type': i.content_type if i.content_type in
                 ('post', 'comment', 'listing') else 'post', 'lang': lang, 'intent': intent, 'synthetic': True}
                for i in items if i.text.strip()]


async def main(per_cell, out):
    client = anthropic.AsyncAnthropic(api_key=os.environ['ANTHROPIC_API_KEY'], max_retries=3)
    sem = asyncio.Semaphore(6)
    jobs = [cell(client, i, d, lang, ld, per_cell, sem) for i, d in INTENTS.items() for lang, ld in LANGS.items()]
    rows = [r for group in await asyncio.gather(*jobs) for r in group]
    seen, unique = set(), []
    for r in rows:
        key = r['text'].lower()
        if key not in seen:
            seen.add(key)
            unique.append(r)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', encoding='utf-8') as f:
        for i, r in enumerate(unique):
            f.write(json.dumps({'id': f'syn-{i:05d}', **r}, ensure_ascii=False) + '\n')
    print(f'{len(unique)} items -> {out}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--per-cell', type=int, default=8)
    ap.add_argument('--out', type=Path, default=Path(__file__).parent / 'data' / 'corpus.jsonl')
    a = ap.parse_args()
    asyncio.run(main(a.per_cell, a.out))
