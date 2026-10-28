from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from outbox import reconcile


class Command(BaseCommand):
    help = 'Compare Postgres with the Neo4j projection and repair drift (users, friendships, posts, likes).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Report drift without repairing it.')
        parser.add_argument('--batch', type=int, default=None, help='Ids per range (default GRAPH_RECONCILE_BATCH).')

    def handle(self, *args, dry_run=False, batch=None, **options):
        if not settings.NEO4J_ENABLED:
            raise CommandError('NEO4J_ENABLED is False.')
        result = reconcile.reconcile(batch=batch, repair=not dry_run)
        for kind, n in result.items():
            self.stdout.write(f'{kind}: {n}')
