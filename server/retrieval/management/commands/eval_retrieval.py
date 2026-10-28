"""
Retrieval eval: an ablation of the search stack over the seeded corpus.

    python manage.py seed --users 200 && python manage.py reindex
    python manage.py eval_retrieval [--modes lexical,dense,hybrid,hybrid+rewrite,hybrid+rewrite+rerank]

Relevance is defined by predicates over the seed templates (every phrase in
"all" must appear in the document), so labels are exact and cheap to audit.
Queries are paraphrases, which is what separates lexical from semantic
retrieval. The eval runs as a fresh viewer with no friends or groups, and a
leak check counts any returned item that isn't public: the pass bar is 0.
"""
import json
import math
import time
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from retrieval import documents, hybrid

GOLDEN = Path(__file__).resolve().parents[2] / 'evals' / 'golden_v1.jsonl'
ALL_MODES = ['lexical', 'dense', 'hybrid', 'hybrid+rewrite', 'hybrid+rewrite+rerank']
K = 10


class _Rollback(Exception):
    pass


def _relevant(kind, phrases, universe):
    out = set()
    for oid in universe:
        doc = documents.load(kind, oid)
        if doc and all(p.lower() in doc.text.lower() for p in phrases):
            out.add(oid)
    return out


def _metrics(ranked, relevant):
    top = ranked[:K]
    hits = [1 if r in relevant else 0 for r in top]
    recall = sum(hits) / min(K, len(relevant)) if relevant else 0.0
    rr = next((1 / (i + 1) for i, h in enumerate(hits) if h), 0.0)
    dcg = sum(h / math.log2(i + 2) for i, h in enumerate(hits))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(K, len(relevant))))
    return recall, rr, (dcg / ideal if ideal else 0.0)


def _leaks(kind, ids):
    """Items returned to a friendless outsider that it shouldn't see."""
    if kind == 'posts':
        from posts.models import Post
        return Post.objects.filter(pk__in=ids).exclude(privacy='public', group__isnull=True).exclude(
            privacy='public', group__privacy='public').count()
    if kind == 'groups':
        from groups.models import Group
        return Group.objects.filter(pk__in=ids, privacy='secret').count()
    return 0


class Command(BaseCommand):
    help = 'Run the retrieval ablation and leak check over the seeded corpus.'

    def add_arguments(self, parser):
        parser.add_argument('--modes', default=','.join(ALL_MODES))
        parser.add_argument('--out', default='')

    def handle(self, *args, modes, out, **opts):
        modes = [m for m in modes.split(',') if m]
        unknown = set(modes) - set(ALL_MODES)
        if unknown:
            raise CommandError(f'Unknown modes: {unknown}')
        rows = [json.loads(line) for line in GOLDEN.read_text(encoding='utf-8').splitlines() if line.strip()]
        report = {}
        try:
            with transaction.atomic():
                viewer = get_user_model().objects.create_user(username='retrieval-eval-viewer',
                                                              email='eval@example.test', password=None)
                report = self._run(viewer, rows, modes)
                raise _Rollback
        except _Rollback:
            pass
        lines = ['| mode | recall@10 | MRR | nDCG@10 | p50 latency (s) | leaks |', '|---|---|---|---|---|---|']
        for m, r in report.items():
            lines.append(f"| {m} | {r['recall@10']:.3f} | {r['mrr']:.3f} | {r['ndcg@10']:.3f} | "
                         f"{r['latency_p50_s']:.2f} | {r['leaks']} |")
        self.stdout.write('\n'.join(lines))
        if out:
            Path(out).write_text(json.dumps(report, indent=2), encoding='utf-8')
        if any(r['leaks'] for r in report.values()):
            raise CommandError('Leak check failed: non-public content was returned to an outsider.')

    def _run(self, viewer, rows, modes):
        from core.search import CONTENT
        universes = {k: set(CONTENT[k][0](viewer).values_list('pk', flat=True)) for k in {r['kind'] for r in rows}}
        labels = {r['id']: _relevant(r['kind'], r['all'], universes[r['kind']]) for r in rows}
        empty = [r['id'] for r in rows if not labels[r['id']]]
        if empty:
            self.stderr.write(f'No relevant documents for {empty}; is the corpus seeded? They score 0.')
        report = {}
        for mode in modes:
            base = mode.split('+')[0]
            rewrite = 'rewrite' in mode
            rerank = mode.endswith('rerank')
            recalls, rrs, ndcgs, lats, leaks = [], [], [], [], 0
            for r in rows:
                started = time.monotonic()
                plan = hybrid.Plan(query=r['query']) if base == 'lexical' else \
                    hybrid.plan_query(r['query'], viewer.id, rewrite=rewrite)
                if base != 'lexical' and plan.vector is None:
                    raise CommandError('The AI service is unavailable; only the lexical mode can run.')
                _, hits = hybrid.search(viewer, r['query'], [r['kind']], mode=base, plan=plan, rerank=rerank,
                                        limit=K)
                lats.append(time.monotonic() - started)
                ranked = [h.id for h in hits]
                leaks += _leaks(r['kind'], ranked)
                rec, rr, nd = _metrics(ranked, labels[r['id']])
                recalls.append(rec)
                rrs.append(rr)
                ndcgs.append(nd)
            lats.sort()
            report[mode] = {'recall@10': sum(recalls) / len(rows), 'mrr': sum(rrs) / len(rows),
                            'ndcg@10': sum(ndcgs) / len(rows), 'latency_p50_s': lats[len(lats) // 2],
                            'leaks': leaks, 'queries': len(rows)}
        return report
