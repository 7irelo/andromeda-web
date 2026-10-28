import io
import json

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from chats.models import ChatMember

User = get_user_model()


@pytest.mark.django_db
def test_builds_one_fanout_room_idempotently():
    for i in range(5):
        User.objects.create_user(username=f'demo{i}', password='pass-1234567', email=f'd{i}@x.io')
    out = io.StringIO()
    call_command('seed_loadtest', '--members', '4', '--i-know-this-is-not-production', stdout=out)
    data = json.loads(out.getvalue())
    assert data['members'] == ['demo0', 'demo1', 'demo2', 'demo3']
    call_command('seed_loadtest', '--members', '5', '--i-know-this-is-not-production', stdout=io.StringIO())
    assert ChatMember.objects.filter(room_id=data['room_id']).count() == 5


@pytest.mark.django_db
def test_refuses_without_debug_or_flag(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command('seed_loadtest', stdout=io.StringIO())
