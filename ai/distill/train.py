"""
Step 3: train and evaluate the distilled classifier.

    python -m distill.train --labels distill/data/labels.jsonl --out distill/models/moderation-student.json

Model: text-embedding-3-small vectors -> multinomial logistic regression,
temperature-calibrated on a validation split. It's saved as plain JSON
(coefficients, intercepts, temperature, threshold): no pickles, nothing that
executes on load.

Operating point. The student is only trusted to say "allow": a wrongly
removed post hurts more than a delayed spam post, and anything it isn't sure
about still goes to the LLM pipeline. The allow threshold is the lowest
probability at which, on validation, at most 1% of the items it would wave
through were labelled review or remove by the teacher. We report how much
traffic that skips (coverage) and what it costs.

Evaluation uses the human-labelled dev and held-out sets, never the
synthetic training data.
"""
import argparse
import json
import math
import os
import random
import time
from pathlib import Path

import numpy as np
from openai import OpenAI
from sklearn.linear_model import LogisticRegression

CLASSES = ['allow', 'review', 'remove']
EMBED_MODEL = 'text-embedding-3-small'
MAX_UNSAFE_PASS_RATE = 0.01
DATASETS = Path(__file__).resolve().parents[1] / 'evals' / 'datasets'


def embed(client, texts):
    out = []
    for i in range(0, len(texts), 100):
        res = client.embeddings.create(model=EMBED_MODEL, input=[t[:8000] for t in texts[i:i + 100]])
        out.extend(d.embedding for d in sorted(res.data, key=lambda d: d.index))
    return np.array(out, dtype=np.float32)


def softmax(z):
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def fit_temperature(logits, y):
    best, best_nll = 1.0, float('inf')
    for t in np.linspace(0.3, 5.0, 95):
        p = softmax(logits / t)
        nll = -np.mean(np.log(p[np.arange(len(y)), y] + 1e-12))
        if nll < best_nll:
            best, best_nll = float(t), nll
    return best


def ece(probs, y, bins=10):
    conf, pred = probs.max(axis=1), probs.argmax(axis=1)
    total = 0.0
    for b in range(bins):
        m = (conf > b / bins) & (conf <= (b + 1) / bins)
        if m.any():
            total += m.mean() * abs((pred[m] == y[m]).mean() - conf[m].mean())
    return float(total)


def allow_threshold(p_allow, y):
    """Lowest threshold where <= 1% of waved-through items weren't 'allow'; 1.01 (never) if none qualifies."""
    for t in np.round(np.arange(0.50, 1.0, 0.01), 2):
        passed = p_allow >= t
        if passed.sum() >= 5 and (y[passed] != 0).mean() <= MAX_UNSAFE_PASS_RATE:
            return float(t)
    return 1.01


def per_class(pred, y):
    rows = {}
    for i, c in enumerate(CLASSES):
        tp = int(((pred == i) & (y == i)).sum())
        fp = int(((pred == i) & (y != i)).sum())
        fn = int(((pred != i) & (y == i)).sum())
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        rows[c] = {'precision': round(p, 3), 'recall': round(r, 3),
                   'f1': round(2 * p * r / (p + r), 3) if p + r else 0.0}
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--labels', type=Path, default=Path(__file__).parent / 'data' / 'labels.jsonl')
    ap.add_argument('--out', type=Path, default=Path(__file__).parent / 'models' / 'moderation-student.json')
    ap.add_argument('--seed', type=int, default=7)
    a = ap.parse_args()
    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
    rows = [json.loads(line) for line in a.labels.read_text(encoding='utf-8').splitlines() if line.strip()]
    random.Random(a.seed).shuffle(rows)  # noqa: S311 - a reproducible data split, not security
    split = int(len(rows) * 0.8)
    train, val = rows[:split], rows[split:]

    x_train = embed(client, [r['text'] for r in train])
    x_val = embed(client, [r['text'] for r in val])
    y_train = np.array([CLASSES.index(r['label']) for r in train])
    y_val = np.array([CLASSES.index(r['label']) for r in val])

    clf = LogisticRegression(max_iter=2000, C=4.0, class_weight='balanced')
    clf.fit(x_train, y_train)
    temperature = fit_temperature(clf.decision_function(x_val), y_val)
    p_val = softmax(clf.decision_function(x_val) / temperature)
    threshold = allow_threshold(p_val[:, 0], y_val)

    report = {'trained_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'embedding_model': EMBED_MODEL,
              'train_items': len(train), 'validation_items': len(val), 'teacher': rows[0].get('teacher'),
              'temperature': round(temperature, 3), 'allow_threshold': threshold,
              'validation_vs_teacher': {'accuracy': round(float((p_val.argmax(1) == y_val).mean()), 3),
                                        'ece': round(ece(p_val, y_val), 3)}}

    # Human-labelled sets.
    for name in ('moderation_v2.jsonl', 'moderation_holdout_v1.jsonl'):
        gold = [json.loads(line) for line in (DATASETS / name).read_text(encoding='utf-8').splitlines() if line.strip()]
        started = time.monotonic()
        x = embed(client, [g['text'] for g in gold])
        latency_ms = (time.monotonic() - started) / len(gold) * 1000
        y = np.array([CLASSES.index(g['expected']) for g in gold])
        p = softmax(clf.decision_function(x) / temperature)
        pred = p.argmax(1)
        passed = p[:, 0] >= threshold
        report[name] = {
            'items': len(gold), 'accuracy': round(float((pred == y).mean()), 3),
            'macro_f1': round(float(np.mean([v['f1'] for v in per_class(pred, y).values()])), 3),
            'per_class': per_class(pred, y), 'ece': round(ece(p, y), 3),
            'coverage_at_threshold': round(float(passed.mean()), 3),
            'unsafe_passed_at_threshold': [g['id'] for g, ok in zip(gold, passed, strict=True)
                                           if ok and g['expected'] != 'allow'],
            'embedding_latency_ms_per_item_batched': round(latency_ms, 1),
        }
    # Cost per 1M items at ~60 tokens per item: embeddings only, $0.02 per 1M tokens.
    report['cost_usd_per_1m_items'] = round(60 * 1e6 * 0.02 / 1e6, 2)

    model = {'classes': CLASSES, 'embedding_model': EMBED_MODEL, 'coef': np.round(clf.coef_, 6).tolist(),
             'intercept': np.round(clf.intercept_, 6).tolist(), 'temperature': temperature,
             'allow_threshold': threshold, 'report': report}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(model), encoding='utf-8')
    print(json.dumps(report, indent=2))
    if not math.isfinite(temperature):
        raise SystemExit('Calibration failed')


if __name__ == '__main__':
    main()
