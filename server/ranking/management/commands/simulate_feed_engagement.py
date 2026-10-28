"""
Synthetic feed sessions for the demo accounts, so the ranker can be trained
and evaluated end to end without real users.

    python manage.py seed --users 100
    python manage.py simulate_feed_engagement --days 14
    python manage.py train_ranker --synthetic

Only seed accounts (emails ending ``@example.test``) are touched, as viewers
and as authors, and only with DEBUG on or ``--i-know-this-is-not-production``.
Rows written are flagged ``synthetic`` so they never mix with real data.

On the first run the seed posts, likes and comments (all created "now" by
``seed``) are spread back over the simulated period, so posts have ages and
history to learn from. Each simulated day, active viewers open the feed at a
random time, get the window ranked by their experiment arm's ranker (v2 once a
model exists), scroll a few posts, and engage according to a hidden
ground-truth model: driven by affinity with the author and recency, with
per-viewer and per-(viewer, author) taste plus noise, and a position bias.
Engagements become real likes and comments (dated in the past), so later
days' features see earlier days' behaviour.
"""
import math
import random
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from posts import feed
from posts.models import Comment, HiddenPost, Like, Post

from ... import features, impressions, model_store, serving
from ...models import FeedImpression

SEED_DOMAIN = '@example.test'
F = features.INDEX


def ground_truth_logit(f, taste, position):
    """The hidden engagement model. The ranker never sees ``taste``; it has to infer it from history."""
    if f[F['is_own_post']]:
        return -4.0
    return (-2.6
            + 0.9 * f[F['is_friend']]
            + 0.7 * f[F['author_likes_30d']]
            + 0.6 * f[F['author_comments_30d']]
            + 0.3 * f[F['author_messages_30d']]
            + 0.25 * f[F['shared_groups']]
            + 0.35 * f[F['in_member_group']]
            + 0.2 * f[F['follows_page']]
            - 0.45 * f[F['age_hours']]
            + 0.3 * f[F['friend_engagements']]
            + 0.2 * f[F['post_comments']]
            + 1.2 * f[F['interest_similarity']]
            + 1.5 * (f[F['author_engagement_rate']] - features.RATE_PRIOR)
            + (0.3 if f[F['media_type']] == features.MEDIA_TYPES['image'] else 0.0)
            + taste
            - 0.03 * position)


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


class Command(BaseCommand):
    help = 'Generate synthetic feed impressions and engagement for seed accounts (development only).'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=14)
        parser.add_argument('--until-days-ago', type=int, default=0,
                            help='End the simulated period this many days ago (to leave room for a later run)')
        parser.add_argument('--sessions', type=float, default=0.8, help='Average feed sessions per user per day')
        parser.add_argument('--seed', type=int, default=7)
        parser.add_argument('--backdate', choices=['auto', 'yes', 'no'], default='auto',
                            help='Spread seed content over the period (auto: only on the first run)')
        parser.add_argument('--i-know-this-is-not-production', action='store_true', dest='force')

    def handle(self, *args, days, until_days_ago, sessions, seed, backdate, force, **options):
        if not settings.DEBUG and not force:
            raise CommandError('Refusing to simulate with DEBUG off. Pass --i-know-this-is-not-production.')
        if not 1 <= days <= 90 or not 0 <= until_days_ago <= 60:
            raise CommandError('--days must be between 1 and 90 and --until-days-ago between 0 and 60.')
        users = list(get_user_model().objects.filter(email__endswith=SEED_DOMAIN, is_active=True))
        if not users:
            raise CommandError('No seed accounts found. Run `manage.py seed` first.')
        seed_ids = {u.id for u in users}
        rng = random.Random(seed)
        now = timezone.now()
        end = now - timedelta(days=until_days_ago, minutes=5)
        start = end - timedelta(days=days)

        first_run = not FeedImpression.objects.filter(synthetic=True).exists()
        if backdate == 'yes' or (backdate == 'auto' and first_run):
            self._backdate(rng, seed_ids, start, now)

        activity = {u.id: rng.uniform(0.2, 1.6) for u in users}
        user_taste = {u.id: rng.gauss(0, 0.4) for u in users}
        pair_taste = {}
        model_store.reset()
        totals = {'sessions': 0, 'impressions': 0, 'engaged': 0, 'v2_sessions': 0}

        for day in range(days):
            day_start = start + timedelta(days=day)
            new_likes, new_comments, hides = [], [], []
            for user in users:
                n = self._poisson(rng, sessions * activity[user.id])
                for _ in range(n):
                    t = day_start + timedelta(seconds=rng.uniform(0, 86400))
                    if t >= end:
                        continue
                    stats = self._session(rng, user, t, seed_ids, user_taste, pair_taste,
                                          new_likes, new_comments, hides)
                    for k, v in stats.items():
                        totals[k] += v
            with transaction.atomic():
                self._write_engagement(new_likes, new_comments, hides)
            self.stdout.write(f'  day {day + 1}/{days}: {totals["impressions"]} impressions so far')

        self._recount(seed_ids)
        rate = totals['engaged'] / totals['impressions'] if totals['impressions'] else 0
        self.stdout.write(self.style.WARNING('SYNTHETIC DATA: generated by a simulated engagement model, '
                                             'not real user behaviour.'))
        self.stdout.write(self.style.SUCCESS(
            f'Simulated {totals["sessions"]} sessions ({totals["v2_sessions"]} ranked by v2) over {days} days: '
            f'{totals["impressions"]} impressions, engagement rate {rate:.1%}.'))

    @staticmethod
    def _poisson(rng, lam):
        # Knuth; lam is small.
        limit, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= rng.random()
            if p <= limit:
                return k
            k += 1

    def _backdate(self, rng, seed_ids, start, now):
        span = (now - start).total_seconds() + 3 * 86400
        posts = list(Post.objects.filter(author_id__in=seed_ids).only('id', 'created_at'))
        for p in posts:
            p.created_at = now - timedelta(seconds=rng.uniform(0, span))
        Post.objects.bulk_update(posts, ['created_at'], batch_size=500)
        created = {p.id: p.created_at for p in posts}
        for model, who in ((Like, 'user_id'), (Comment, 'author_id')):
            rows = list(model.objects.filter(post_id__in=created, **{f'{who}__in': seed_ids}).only('id', 'post_id'))
            for r in rows:
                base = created[r.post_id]
                r.created_at = base + timedelta(seconds=rng.uniform(0, min(48 * 3600, (now - base).total_seconds())))
            model.objects.bulk_update(rows, ['created_at'], batch_size=500)
        self.stdout.write(f'Spread {len(posts)} seed posts and their likes/comments over the period.')

    def _session(self, rng, user, t, seed_ids, user_taste, pair_taste, new_likes, new_comments, hides):
        rows = [r for r in feed.candidate_window(user, t) if r[1] in seed_ids]
        if not rows:
            return {}
        variant = serving.assigned_variant(user)
        ranked = serving.score(user, feed.as_candidates(rows), t) if variant == 'v2' else None
        if ranked is not None:
            order, feats, ranker, version = ranked.ids, ranked.features, 'v2', ranked.model_version
        else:
            scored, _ = feed.rank_v1(user, rows, t)
            order, feats, ranker, version = [r[0] for r in scored], None, 'v1', ''
        seen = order[:rng.randint(5, 25)]
        by_id = {r[0]: r for r in rows}
        if feats is None:
            X = features.build(user, feed.as_candidates([by_id[i] for i in seen]), t)
            feats = {pid: X[i].tolist() for i, pid in enumerate(seen)}
        posts = [Post(id=pid) for pid in seen]
        logged = impressions.log_page(user, posts, first_position=0, variant=variant, ranker=ranker,
                                      model_version=version, features_by_id=feats, served_at=t, synthetic=True)
        engaged = []
        for imp in logged:
            author = by_id[imp.post_id][1]
            taste = user_taste[user.id] + pair_taste.setdefault((user.id, author), rng.gauss(0, 0.7))
            p = sigmoid(ground_truth_logit(imp.features, taste, imp.position) + rng.gauss(0, 0.3))
            imp.dwell_ms = int(rng.lognormvariate(7.6 if rng.random() < p else 6.6, 0.6))
            if rng.random() < p:
                imp.engaged = True
                imp.engaged_at = t + timedelta(seconds=rng.expovariate(1 / 300))
                engaged.append(imp)
                kind = rng.random()
                if kind < 0.6:
                    new_likes.append((user.id, imp.post_id, imp.engaged_at))
                elif kind < 0.8:
                    new_comments.append((user.id, imp.post_id, imp.engaged_at))
            elif p < 0.03 and rng.random() < 0.02:
                hides.append((user.id, imp.post_id))
        FeedImpression.objects.bulk_update(logged, ['engaged', 'engaged_at', 'dwell_ms'])
        return {'sessions': 1, 'impressions': len(logged), 'engaged': len(engaged), 'v2_sessions': int(ranker == 'v2')}

    @staticmethod
    def _write_engagement(new_likes, new_comments, hides):
        # bulk_create sets auto_now_add to "now"; the simulated times are applied afterwards.
        existing = set(Like.objects.filter(user_id__in={u for u, _, _ in new_likes},
                                           post_id__in={p for _, p, _ in new_likes}).values_list('user_id', 'post_id'))
        likes = {}
        for u, p, when in new_likes:
            if (u, p) not in existing:
                likes.setdefault((u, p), when)
        made = Like.objects.bulk_create([Like(user_id=u, post_id=p) for u, p in likes])
        for obj in made:
            obj.created_at = likes[(obj.user_id, obj.post_id)]
        Like.objects.bulk_update(made, ['created_at'], batch_size=500)
        comments = Comment.objects.bulk_create([Comment(author_id=u, post_id=p, content='Nice one!')
                                                for u, p, _ in new_comments])
        for obj, (_, _, when) in zip(comments, new_comments, strict=True):
            obj.created_at = when
        Comment.objects.bulk_update(comments, ['created_at'], batch_size=500)
        HiddenPost.objects.bulk_create([HiddenPost(user_id=u, post_id=p) for u, p in set(hides)],
                                       ignore_conflicts=True)

    @staticmethod
    def _recount(seed_ids):
        from django.db.models import Count
        posts = list(Post.objects.filter(author_id__in=seed_ids)
                     .annotate(n_likes=Count('likes', distinct=True), n_comments=Count('comments', distinct=True)))
        for p in posts:
            p.likes_count, p.comments_count = p.n_likes, p.n_comments
        Post.objects.bulk_update(posts, ['likes_count', 'comments_count'], batch_size=500)
