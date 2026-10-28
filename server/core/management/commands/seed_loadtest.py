"""
Load-test fixtures on top of ``manage.py seed``: one group chat with many
members for the WebSocket fan-out test. Prints JSON for the k6 scripts.

    python manage.py seed --users 200
    python manage.py seed_loadtest --members 100

Refuses to run unless DEBUG is on or --i-know-this-is-not-production is passed,
for the same reason as ``seed``: every seeded account shares one password.
"""
import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from chats.models import ChatMember, ChatRoom

ROOM_NAME = 'k6 fan-out'


class Command(BaseCommand):
    help = 'Create a large group chat of seeded demo users for the k6 WebSocket fan-out test.'

    def add_arguments(self, parser):
        parser.add_argument('--members', type=int, default=100)
        parser.add_argument('--i-know-this-is-not-production', action='store_true', dest='force')

    def handle(self, *args, members, force, **options):
        if not (settings.DEBUG or force):
            raise CommandError('Refusing to seed load-test data with DEBUG off (pass --i-know-this-is-not-production).')
        users = list(get_user_model().objects.filter(username__startswith='demo', is_active=True)
                     .order_by('id')[:members])
        if len(users) < 2:
            raise CommandError('Run `manage.py seed --users N` first.')
        with transaction.atomic():
            room = ChatRoom.objects.filter(name=ROOM_NAME, room_type='group').first()
            if room is None:
                room = ChatRoom.objects.create(name=ROOM_NAME, room_type='group', created_by=users[0])
            existing = set(ChatMember.objects.filter(room=room).values_list('user_id', flat=True))
            ChatMember.objects.bulk_create([ChatMember(room=room, user=u, role='admin' if i == 0 else 'member')
                                            for i, u in enumerate(users) if u.id not in existing])
        self.stdout.write(json.dumps({'room_id': room.id, 'members': [u.username for u in users]}))
