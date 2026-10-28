"""
Train ranker v2 from logged feed impressions.

    python manage.py train_ranker                 # real impressions, last 30 days
    python manage.py train_ranker --synthetic     # impressions from simulate_feed_engagement

Splits by time (train / validation / test), trains LightGBM with early
stopping on validation, calibrates on validation, reports test-split AUC,
log-loss and calibration against the v1 heuristic, and saves the model and
its metadata to ``private/models/``. Serving picks it up within a minute.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ... import features, model_store, training
from ...models import FeedImpression
from ...tasks import fill_features


class Command(BaseCommand):
    help = 'Train the LightGBM feed ranker (v2) from feed impressions.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30, help='Data window in days')
        parser.add_argument('--synthetic', action='store_true',
                            help='Train on synthetic impressions (simulate_feed_engagement) instead of real ones')
        parser.add_argument('--min-rows', type=int, default=200)
        parser.add_argument('--dry-run', action='store_true', help='Train and report, but do not save the model')

    def handle(self, *args, days, synthetic, min_rows, dry_run, **options):
        now = timezone.now()
        since = now - timedelta(days=days)
        self._backfill(since, synthetic)
        X, y, t = training.load_dataset(since, now, synthetic=synthetic)
        label = 'SYNTHETIC' if synthetic else 'real'
        self.stdout.write(f'Dataset: {len(y)} matured {label} impressions, {int(y.sum()) if len(y) else 0} engaged.')
        try:
            booster, report = training.train(X, y, t, min_rows=min_rows)
        except training.NotEnoughData as exc:
            raise CommandError(str(exc))

        self._print_report(report, synthetic)
        if dry_run:
            self.stdout.write('Dry run: model not saved.')
            return
        stamp = now.strftime('%Y%m%dT%H%M%S%fZ')
        meta = {
            'version': f'ranker-{stamp}',
            'trained_at': now.isoformat(),
            'feature_version': features.FEATURE_VERSION,
            'features': features.FEATURES,
            'categorical': features.CATEGORICAL,
            'synthetic': synthetic,
            'label': 'engaged within 24h (like, comment, save, share, open)',
            **report,
        }
        name = model_store.save(booster.model_to_string(num_iteration=report['best_iteration']), meta, stamp)
        self.stdout.write(self.style.SUCCESS(f'Saved {name}'))

    def _backfill(self, since, synthetic):
        """Impressions whose features were to be filled in the background but weren't yet (e.g. worker down)."""
        pending = (FeedImpression.objects.filter(served_at__gte=since, synthetic=synthetic, features__isnull=True)
                   .select_related('viewer', 'post'))
        total = 0
        while True:
            batch = list(pending[:2000])
            if not batch:
                break
            total += fill_features(batch)
        if total:
            self.stdout.write(f'Computed features for {total} impressions logged without them.')

    def _print_report(self, report, synthetic):
        out = self.stdout.write
        if synthetic:
            out(self.style.WARNING('=' * 72))
            out(self.style.WARNING('SYNTHETIC DATA: these metrics come from simulated engagement and say '
                                   'nothing about real users.'))
            out(self.style.WARNING('=' * 72))
        rows, window = report['rows'], report['data_window']
        for split in ('train', 'validation', 'test'):
            out(f'  {split:<10} {rows[split]:>7} rows  {window[split][0][:16]} to {window[split][1][:16]}')
        out(f'  best iteration: {report["best_iteration"]}')
        m, b = report['metrics']['model'], report['metrics']['baseline_v1']
        out('')
        out(f'Test split ({m["n"]} impressions, {m["positives"]} engaged)')
        out(f'  {"":<26}{"AUC":>8}{"log-loss":>10}{"ECE":>8}')
        for name, r in (('ranker v2 (LightGBM)', m), ('baseline v1 heuristic*', b)):
            auc = f'{r["auc"]:.4f}' if r['auc'] is not None else 'n/a'
            out(f'  {name:<26}{auc:>8}{r["log_loss"]:>10.4f}{r["ece"]:>8.4f}')
        out('  * v1 score calibrated the same way on the validation split, so log-loss/ECE are comparable.')
        out('')
        out('Reliability (ranker v2, test split)')
        out(f'  {"bin":<12}{"n":>7}{"predicted":>11}{"observed":>10}')
        for r in m['reliability']:
            pred = f'{r["predicted"]:.3f}' if r['predicted'] is not None else '-'
            obs = f'{r["observed"]:.3f}' if r['observed'] is not None else '-'
            out(f'  {r["lo"]:.1f}-{r["hi"]:.1f}{"":<5}{r["n"]:>7}{pred:>11}{obs:>10}')
        out('')
        out('Feature importance (gain)')
        for name, gain in sorted(report['feature_importance_gain'].items(), key=lambda kv: -kv[1]):
            out(f'  {name:<24}{gain:>12.1f}')
