"""
Read out an A/B experiment from feed impressions.

    python manage.py ab_report feed_ranker [--days 14] [--synthetic]

Per arm: impressions, engagement rate, and guardrails (posts hidden and
reported per 1,000 impressions, distinct active days per user as a session
proxy), then a two-proportion z-test and a 95% confidence interval for the
difference in engagement rate between the arms.

Arms are compared by assignment (intent to treat): a v2 viewer whose page fell
back to v1 still counts as v2, so a fragile ranker can't look better by
failing on the hard cases. The fallback share is shown per arm.
"""
import math
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from posts.models import HiddenPost

from ...models import FeedImpression
from ...serving import EXPERIMENT


def normal_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def two_proportion(k1, n1, k2, n2):
    """z, two-sided p-value (pooled), and the 95% CI of p2 - p1 (unpooled Wald)."""
    if not (n1 and n2):
        return None
    p1, p2 = k1 / n1, k2 / n2
    pooled = (k1 + k2) / (n1 + n2)
    se_pooled = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    z = (p2 - p1) / se_pooled if se_pooled else 0.0
    p_value = 2 * (1 - normal_cdf(abs(z)))
    se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    diff = p2 - p1
    return {'z': z, 'p_value': p_value, 'diff': diff, 'ci': (diff - 1.96 * se, diff + 1.96 * se)}


class Command(BaseCommand):
    help = 'Per-variant engagement, guardrails and significance for an experiment (feed_ranker).'

    def add_arguments(self, parser):
        parser.add_argument('experiment')
        parser.add_argument('--days', type=int, default=14)
        parser.add_argument('--synthetic', action='store_true', help='Report on simulate_feed_engagement data')

    def handle(self, *args, experiment, days, synthetic, **options):
        if experiment != EXPERIMENT:
            raise CommandError(f'Unknown experiment {experiment!r}. Known: {EXPERIMENT}.')
        since = timezone.now() - timedelta(days=days)
        imps = FeedImpression.objects.filter(served_at__gte=since, synthetic=synthetic).exclude(variant='')
        arms = {r['variant']: r for r in imps.values('variant').annotate(
            n=Count('id'), k=Count('id', filter=Q(engaged=True)), users=Count('viewer', distinct=True))}
        if not arms:
            raise CommandError('No impressions for this experiment in the window.')
        for variant, arm in arms.items():
            # Pages ordered by another ranker than the arm's (the chronological tail past the window is shared).
            arm['fallback'] = (imps.filter(variant=variant)
                               .exclude(ranker__in=[variant, FeedImpression.RANKER_LATEST]).count())
            viewers = imps.filter(variant=variant).values('viewer_id')
            served = imps.filter(variant=variant).values('post_id')
            arm['hides'] = HiddenPost.objects.filter(user_id__in=viewers, post_id__in=served,
                                                     created_at__gte=since).count()
            arm['reports'] = self._reports(viewers, served, since)
            days_active = (imps.filter(variant=variant).annotate(day=TruncDate('served_at'))
                           .values('viewer_id', 'day').distinct().count())
            arm['days_per_user'] = days_active / arm['users'] if arm['users'] else 0.0

        out = self.stdout.write
        if synthetic:
            out(self.style.WARNING('SYNTHETIC DATA: simulated engagement, not real users.'))
        out(f'Experiment {experiment}, last {days} days')
        out(f'  {"arm":<5}{"users":>7}{"impressions":>13}{"engaged":>9}{"rate":>8}{"fallback":>10}'
            f'{"hides/1k":>10}{"reports/1k":>12}{"days/user":>11}')
        for variant in sorted(arms):
            a = arms[variant]
            rate = a['k'] / a['n'] if a['n'] else 0.0
            out(f'  {variant:<5}{a["users"]:>7}{a["n"]:>13}{a["k"]:>9}{rate:>8.2%}{a["fallback"] / a["n"]:>10.1%}'
                f'{1000 * a["hides"] / a["n"]:>10.2f}{1000 * a["reports"] / a["n"]:>12.2f}{a["days_per_user"]:>11.2f}')

        if {'v1', 'v2'} <= arms.keys():
            v1, v2 = arms['v1'], arms['v2']
            t = two_proportion(v1['k'], v1['n'], v2['k'], v2['n'])
            out('')
            out(f'Engagement rate v2 - v1: {t["diff"]:+.2%} (95% CI {t["ci"][0]:+.2%} to {t["ci"][1]:+.2%}), '
                f'z = {t["z"]:.2f}, p = {t["p_value"]:.4f}')
            out('  Impressions within a user are correlated, so this test is optimistic; treat p-values near '
                '0.05 with care.')
        else:
            out('Both arms need impressions for a comparison.')

    @staticmethod
    def _reports(viewers, served, since):
        try:
            from moderation.models import Report
        except ImportError:
            return 0
        return Report.objects.filter(reporter_id__in=viewers, content_type='post', object_id__in=served,
                                     created_at__gte=since).count()
