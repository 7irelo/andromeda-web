"""'Catch me up': who can ask, and whose messages may reach the model."""
import pytest

from chats.models import ChatMember, ChatRoom, Message
from core import ai_client
from core.test_security import client_for, make_user
from users.models import Block

SUMMARY = {'summary': {'tldr': 'ok', 'topics': [], 'decisions': [], 'questions_for_you': []}, 'model': 'fake',
           'cost_usd': 0, 'cited_ids_dropped': 0}


@pytest.fixture
def room(db):
    alice, bob, carol = make_user('alice'), make_user('bob'), make_user('carol')
    r = ChatRoom.objects.create(room_type='group', name='Braai', created_by=alice)
    for u in (alice, bob, carol):
        ChatMember.objects.create(room=r, user=u)
    for sender, text in ((alice, 'hi all'), (bob, 'bob here'), (carol, 'carol here'), (bob, 'saturday?')):
        Message.objects.create(room=r, sender=sender, content=text)
    return r, alice, bob, carol


@pytest.fixture
def ai(monkeypatch):
    calls = []
    monkeypatch.setattr(ai_client, 'enabled', lambda: True)
    monkeypatch.setattr(ai_client, 'call', lambda path, payload, user_id: calls.append(payload) or SUMMARY)
    return calls


def url(r):
    return f'/api/chats/rooms/{r.id}/catch_up/'


def test_non_members_cannot_catch_up(room, ai):
    r, *_ = room
    assert client_for(make_user('mallory')).post(url(r)).status_code == 404
    assert ai == []


def test_opted_out_viewer_is_refused(room, ai):
    r, alice, *_ = room
    alice.ai_opt_out = True
    alice.save()
    assert client_for(alice).post(url(r)).status_code == 403 and ai == []


def test_opted_out_and_blocked_senders_never_reach_the_model(room, ai):
    r, alice, bob, carol = room
    carol.ai_opt_out = True
    carol.save()
    Block.objects.create(blocker=alice, blocked=bob)
    assert client_for(alice).post(url(r)).status_code == 200
    texts = [m['text'] for m in ai[0]['messages']]
    assert texts == ['hi all']
