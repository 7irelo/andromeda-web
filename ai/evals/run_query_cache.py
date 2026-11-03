"""
Semantic cache eval: choose the similarity threshold by measuring false hits.

    python -m evals.run_query_cache

Each pair is either the same search intent (a hit saves a rewrite) or a near
miss (a hit returns the wrong results). Only embeddings are called. A false hit
is worse than a miss, so the recommended threshold is the lowest with none.
"""
import json
import os
from pathlib import Path

from openai import OpenAI

from app.features.query_cache import shorten, similarity

DATASET = Path(__file__).parent / 'datasets' / 'query_cache_v1.jsonl'
MODEL = 'text-embedding-3-small'


def main():
    pairs = [json.loads(line) for line in DATASET.read_text(encoding='utf-8').splitlines() if line.strip()]
    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
    texts = sorted({p['a'] for p in pairs} | {p['b'] for p in pairs})
    res = client.embeddings.create(model=MODEL, input=texts)
    vectors = {t: shorten(d.embedding) for t, d in zip(texts, sorted(res.data, key=lambda d: d.index), strict=True)}
    scored = [(similarity(vectors[p['a']], vectors[p['b']]), p) for p in pairs]
    same = sum(p['same_intent'] for _, p in scored)
    near = len(scored) - same

    print(f'{len(pairs)} pairs: {same} same intent, {near} near misses')
    print('threshold  hit rate  false hits')
    recommended = None
    for t in (0.80, 0.84, 0.86, 0.88, 0.90, 0.92, 0.94, 0.96, 0.98):
        hits = sum(s >= t for s, p in scored if p['same_intent'])
        false_hits = sum(s >= t for s, p in scored if not p['same_intent'])
        print(f'{t:9.2f}  {hits / same:8.2f}  {false_hits:>3} / {near}')
        if false_hits == 0 and recommended is None:
            recommended = t
    print(f'Recommended threshold (no false hits): {recommended}')
    print('Closest near misses:')
    for s, p in sorted(((s, p) for s, p in scored if not p['same_intent']), key=lambda x: -x[0])[:5]:
        print(f"  {s:.3f}  {p['a']!r} / {p['b']!r}")


if __name__ == '__main__':
    main()
