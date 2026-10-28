"""
Smart-reply acceptance per A/B variant.

    python manage.py reply_metrics            # last 30 days
    python manage.py reply_metrics --days 7

A "set" is one row of suggestions shown to one user for one message. The
acceptance rate is the share of sets where the user sent a suggestion,
verbatim or edited; the verbatim rate counts only unchanged sends.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from chats.models import ReplySuggestionEvent as Event

GROUP = ('variant', 'user_id', 'room_id', 'anchor_message_id')


def _sets(qs):
    return qs.values(*GROUP).distinct().count()


def acceptance_by_variant(since):
    events = Event.objects.filter(created_at__gte=since)
    rows = []
    for variant in sorted(set(events.values_list('variant', flat=True))):
        mine = events.filter(variant=variant)
        shown = _sets(mine.filter(action=Event.ACTION_SHOWN))
        accepted = _sets(mine.filter(action=Event.ACTION_ACCEPTED))
        edited = _sets(mine.filter(action=Event.ACTION_EDITED))
        dismissed = _sets(mine.filter(action=Event.ACTION_DISMISSED))
        rows.append({
            'variant': variant, 'sets_shown': shown, 'accepted': accepted, 'edited': edited, 'dismissed': dismissed,
            'acceptance_rate': (accepted + edited) / shown if shown else 0.0,
            'verbatim_rate': accepted / shown if shown else 0.0,
        })
    return rows


class Command(BaseCommand):
    help = 'Print smart-reply acceptance rates per A/B variant.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30)

    def handle(self, *args, days, **options):
        rows = acceptance_by_variant(timezone.now() - timedelta(days=max(days, 1)))
        if not rows:
            self.stdout.write('No smart-reply events in this period.')
            return
        self.stdout.write(f'{"variant":<10} {"shown":>7} {"accepted":>9} {"edited":>7} {"dismissed":>10} '
                          f'{"acceptance":>11} {"verbatim":>9}')
        for r in rows:
            self.stdout.write(f'{r["variant"]:<10} {r["sets_shown"]:>7} {r["accepted"]:>9} {r["edited"]:>7} '
                              f'{r["dismissed"]:>10} {r["acceptance_rate"]:>10.1%} {r["verbatim_rate"]:>9.1%}')
