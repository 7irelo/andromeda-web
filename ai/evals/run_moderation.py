"""
Moderation eval: run the real workflow over the golden set and report quality,
cost and latency.

    python -m evals.run_moderation                 # live (reads keys from the environment)
    python -m evals.run_moderation --gate 0.85     # exit 1 if macro-F1 drops below the gate

"Severe miss" means a 'remove' item that was allowed: the costliest error, so
it's reported separately and must stay at zero.
"""
import argparse
import asyncio
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

from app.budget import Budget
from app.features.moderation import ModerationRequest, moderate
from app.gateway import Gateway
from app.providers import AnthropicProvider, OpenAIProvider

DATASETS = Path(__file__).parent / 'datasets'
LABELS = ['allow', 'review', 'remove']


def f1(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


async def run(concurrency: int, dataset: Path):
    import os
    providers, stage0 = {}, None
    if os.environ.get('ANTHROPIC_API_KEY'):
        providers['anthropic'] = AnthropicProvider(os.environ['ANTHROPIC_API_KEY'], 30)
    if os.environ.get('OPENAI_API_KEY'):
        stage0 = OpenAIProvider(os.environ['OPENAI_API_KEY'], 30)
        providers['openai'] = stage0
    gateway = Gateway(providers=providers, budget=Budget(10**9))
    rows = [json.loads(line) for line in dataset.read_text(encoding='utf-8').splitlines() if line.strip()]
    sem = asyncio.Semaphore(concurrency)

    async def one(row):
        async with sem:
            t0 = time.monotonic()
            res = await moderate(ModerationRequest(content_type=row['content_type'], text=row['text']),
                                 gateway, user_id=0, stage0_provider=stage0)
            return row, res, time.monotonic() - t0

    return await asyncio.gather(*(one(r) for r in rows))


def report(results):
    confusion = Counter((row['expected'], res.decision.value) for row, res, _ in results)
    lines = ['| label | precision | recall | F1 |', '|---|---|---|---|']
    f1s = []
    for label in LABELS:
        tp = confusion[(label, label)]
        fp = sum(v for (e, p), v in confusion.items() if p == label and e != label)
        fn = sum(v for (e, p), v in confusion.items() if e == label and p != label)
        p, r, f = f1(tp, fp, fn)
        f1s.append(f)
        lines.append(f'| {label} | {p:.2f} | {r:.2f} | {f:.2f} |')
    accuracy = sum(confusion[(lbl, lbl)] for lbl in LABELS) / len(results)
    severe = [row['id'] for row, res, _ in results if row['expected'] == 'remove' and res.decision.value == 'allow']
    false_removals = [row['id'] for row, res, _ in results
                      if row['expected'] == 'allow' and res.decision.value == 'remove']
    latencies = sorted(lat for *_, lat in results)
    cost = sum(res.cost_usd for _, res, _ in results)
    escalated = sum(1 for _, res, _ in results if len([s for s in res.stages if s.startswith(('claude', 'gpt'))]) > 1)
    summary = {
        'items': len(results), 'accuracy': round(accuracy, 3), 'macro_f1': round(statistics.mean(f1s), 3),
        'severe_misses': severe, 'false_removals': false_removals, 'escalation_rate': round(escalated / len(results), 3),
        'cost_usd_total': round(cost, 5), 'cost_usd_per_1k_items': round(cost / len(results) * 1000, 3),
        'latency_p50_s': round(latencies[len(latencies) // 2], 2),
        'latency_p95_s': round(latencies[int(len(latencies) * 0.95) - 1], 2),
        'degraded': sum(1 for _, res, _ in results if res.degraded),
    }
    mistakes = [f"- {row['id']} expected **{row['expected']}**, got **{res.decision.value}** "
                f"({', '.join(res.categories) or 'none'}): {res.reason}"
                for row, res, _ in results if row['expected'] != res.decision.value]
    return summary, '\n'.join(lines), mistakes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--gate', type=float, default=None, help='Minimum macro-F1')
    ap.add_argument('--concurrency', type=int, default=4)
    ap.add_argument('--dataset', default='moderation_v2.jsonl', help='File under evals/datasets/')
    args = ap.parse_args()
    results = asyncio.run(run(args.concurrency, DATASETS / args.dataset))
    summary, table, mistakes = report(results)
    out = Path(__file__).parent / 'results'
    out.mkdir(exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M%S')
    (out / f'moderation-{stamp}.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))
    print(table)
    print('\n'.join(mistakes) or 'No mistakes.')
    if args.gate is not None and (summary['macro_f1'] < args.gate or summary['severe_misses']):
        sys.exit(1)


if __name__ == '__main__':
    main()
