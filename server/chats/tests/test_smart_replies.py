"""Smart replies: authorization, privacy of what's sent to the model, feedback logging, metrics and SFT export."""
import io
import json
from datetime import timedelta
from unittest import mock

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from chats import smart_replies
from chats.models import Message, ReplySuggestionEvent, SeedReplySuggestion
from core import ai_client
from users.models import Block

from .helpers import client_for, make_room, make_user

SUGGESTIONS = ['Sounds good!', 'What time?', "Can't make it, sorry"]


@pytest.fixture
def ai_on(settings):
    settings.AI_SERVICE_URL = 'http://ai.internal'
    settings.AI_SERVICE_SECRET = 's' * 40


@pytest.fixture
def alice(db):
    return make_user('alice', first_name='Alice', last_name='Mokoena')


@pytest.fixture
def bob(db):
    return make_user('bob', first_name='Bob')


@pytest.fixture
def room(alice, bob):
    r = make_room(alice, bob)
    Message.objects.create(room=r, sender=bob, content='Braai on Saturday?')
    Message.objects.create(room=r, sender=alice, content='Maybe')
    Message.objects.create(room=r, sender=bob, content='Bring wood if you come')
    return r


def ai_replies(suggestions=SUGGESTIONS, **extra):
    return mock.patch('core.ai_client.call', return_value={'suggestions': suggestions, 'model': 'claude-haiku-5-5',
                                                            'variant': 'haiku', 'cost_usd': 0.0001, **extra})


def suggest(user, room_id):
    c = client_for(user) if user else APIClient()
    return c.post(reverse('chatroom-suggest-replies', kwargs={'pk': room_id}), {}, format='json')


def feedback(user, room_id, action, ids):
    return client_for(user).post(reverse('chatroom-reply-feedback', kwargs={'pk': room_id}),
                                 {'action': action, 'suggestion_ids': ids}, format='json')


# ── Authorization ────────────────────────────────────────────────────────────

class TestSmartReplyAuthorization:
    def test_member_gets_three_suggestions_and_shown_events(self, alice, room, ai_on):
        with ai_replies() as call:
            r = suggest(alice, room.id)
        assert r.status_code == 200
        assert [s['text'] for s in r.data['suggestions']] == SUGGESTIONS
        assert r.data['variant'] in ('haiku', 'luna')
        path, payload = call.call_args.args
        assert path == '/v1/replies' and call.call_args.kwargs['user_id'] == alice.id
        assert payload['viewer'] == 'Alice Mokoena' and payload['variant'] == r.data['variant']
        assert [m['text'] for m in payload['messages']] == ['Braai on Saturday?', 'Maybe', 'Bring wood if you come']
        assert [m['is_viewer'] for m in payload['messages']] == [False, True, False]
        events = ReplySuggestionEvent.objects.filter(user=alice, room=room)
        assert events.count() == 3 and {e.action for e in events} == {'shown'}
        assert {e.suggestion_hash for e in events} == {s['id'] for s in r.data['suggestions']}
        assert all(e.anchor_message_id == room.messages.order_by('-id').first().id for e in events)

    def test_non_member_gets_404_and_nothing_is_sent(self, room, ai_on, db):
        mallory = make_user('mallory')
        with ai_replies() as call:
            assert suggest(mallory, room.id).status_code == 404
            assert feedback(mallory, room.id, 'dismissed', ['a' * 64]).status_code == 404
        call.assert_not_called()

    def test_anonymous_is_rejected(self, room, ai_on):
        with ai_replies() as call:
            assert suggest(None, room.id).status_code == 401
        call.assert_not_called()

    def test_opted_out_member_gets_403(self, alice, room, ai_on):
        alice.ai_opt_out = True
        alice.save(update_fields=['ai_opt_out'])
        with ai_replies() as call:
            assert suggest(alice, room.id).status_code == 403
            assert feedback(alice, room.id, 'dismissed', ['a' * 64]).status_code == 403
        call.assert_not_called()

    def test_blocked_users_messages_are_never_sent(self, alice, bob, room, ai_on):
        carol = make_user('carol')
        room.chatmember_set.create(user=carol)
        Message.objects.create(room=room, sender=carol, content='my secret plan')
        Block.objects.create(blocker=carol, blocked=alice)  # blocks hide content both ways
        with ai_replies() as call:
            suggest(alice, room.id)
        texts = [m['text'] for m in call.call_args.args[1]['messages']]
        assert 'my secret plan' not in texts and 'Bring wood if you come' in texts

    def test_opted_out_members_messages_are_never_sent(self, alice, bob, room, ai_on):
        carol = make_user('carol', ai_opt_out=True)
        room.chatmember_set.create(user=carol)
        Message.objects.create(room=room, sender=carol, content='keep me out of AI')
        with ai_replies() as call:
            suggest(alice, room.id)
        texts = [m['text'] for m in call.call_args.args[1]['messages']]
        assert 'keep me out of AI' not in texts and 'Bring wood if you come' in texts

    def test_dm_with_a_blocked_user_skips_the_model(self, alice, bob, ai_on):
        dm = make_room(alice, bob, room_type='direct')
        Message.objects.create(room=dm, sender=bob, content='hi')
        Block.objects.create(blocker=alice, blocked=bob)
        with ai_replies() as call:
            r = suggest(alice, dm.id)
        assert r.status_code == 200 and r.data['suggestions'] == []
        call.assert_not_called()

    def test_only_this_rooms_latest_messages_are_sent(self, alice, bob, room, ai_on):
        other = make_room(alice, bob, name='Other')
        Message.objects.create(room=other, sender=bob, content='from another chat')
        for i in range(25):
            Message.objects.create(room=room, sender=bob, content=f'msg {i}')
        Message.objects.create(room=room, sender=bob, content='gone', is_deleted=True)
        with ai_replies() as call:
            suggest(alice, room.id)
        msgs = call.call_args.args[1]['messages']
        assert len(msgs) == 20 and msgs[-1]['text'] == 'msg 24'
        assert all(m['text'] not in ('from another chat', 'gone') for m in msgs)
        assert all(Message.objects.get(id=m['id']).room_id == room.id for m in msgs)

    def test_nothing_from_others_means_no_model_call(self, alice, bob, ai_on):
        r = make_room(alice, bob)
        Message.objects.create(room=r, sender=alice, content='hello?')
        with ai_replies() as call:
            assert suggest(alice, r.id).data['suggestions'] == []
        call.assert_not_called()


# ── Behaviour ────────────────────────────────────────────────────────────────

class TestSuggestReplies:
    def test_text_is_never_stored_only_a_keyed_hash(self, alice, room, ai_on):
        with ai_replies():
            r = suggest(alice, room.id)
        h = r.data['suggestions'][0]['id']
        assert len(h) == 64 and h == smart_replies.suggestion_hash('Sounds good!')
        import hashlib
        assert h != hashlib.sha256(b'Sounds good!').hexdigest()  # not reversible with a dictionary
        assert not SeedReplySuggestion.objects.exists()

    def test_output_is_capped_and_deduplicated(self, alice, room, ai_on):
        with ai_replies(['a', 'a', 'b', 'c', 'd', 'x' * 500]):
            r = suggest(alice, room.id)
        assert [s['text'] for s in r.data['suggestions']] == ['a', 'b']

    def test_ai_errors_are_mapped(self, alice, room, ai_on):
        with mock.patch('core.ai_client.call', side_effect=ai_client.AIUnavailable('down')):
            assert suggest(alice, room.id).status_code == 503
        with mock.patch('core.ai_client.call', side_effect=ai_client.AIRejected(429, 'Daily AI allowance used up')):
            assert suggest(alice, room.id).status_code == 429
        assert not ReplySuggestionEvent.objects.exists()

    def test_uses_the_ai_throttle_scope(self, alice, room, ai_on):
        rates = {**ScopedRateThrottle.THROTTLE_RATES, 'ai': '1/min'}
        with mock.patch.object(ScopedRateThrottle, 'THROTTLE_RATES', rates), ai_replies():
            assert suggest(alice, room.id).status_code == 200
            assert suggest(alice, room.id).status_code == 429

    def test_variant_is_sticky_and_configurable(self, alice, room, ai_on, settings):
        settings.SMART_REPLY_VARIANTS = {'haiku': 0, 'luna': 100}
        with ai_replies() as call:
            assert suggest(alice, room.id).data['variant'] == 'luna'
            assert suggest(alice, room.id).data['variant'] == 'luna'
        assert call.call_args.args[1]['variant'] == 'luna'


class TestReplyFeedback:
    def _shown(self, user, room):
        with ai_replies():
            return [s['id'] for s in suggest(user, room.id).data['suggestions']]

    def test_accept_edit_and_dismiss_are_logged_once(self, alice, room, ai_on):
        ids = self._shown(alice, room)
        assert feedback(alice, room.id, 'accepted', [ids[0]]).data == {'recorded': 1}
        assert feedback(alice, room.id, 'accepted', [ids[0]]).data == {'recorded': 0}  # no double counting
        assert feedback(alice, room.id, 'dismissed', ids).data == {'recorded': 2}
        actions = sorted(ReplySuggestionEvent.objects.exclude(action='shown').values_list('action', flat=True))
        assert actions == ['accepted', 'dismissed', 'dismissed']
        assert set(ReplySuggestionEvent.objects.values_list('variant', flat=True)) == {smart_replies.variant_for(alice)}

    def test_feedback_must_match_a_suggestion_shown_to_you_here(self, alice, bob, room, ai_on):
        ids = self._shown(alice, room)
        assert feedback(bob, room.id, 'accepted', [ids[0]]).status_code == 400  # someone else's
        other = make_room(alice, bob, name='Other')
        assert feedback(alice, other.id, 'accepted', [ids[0]]).status_code == 400  # another room
        assert feedback(alice, room.id, 'accepted', ['f' * 64]).status_code == 400  # never shown
        ReplySuggestionEvent.objects.update(created_at=timezone.now() - timedelta(days=2))
        assert feedback(alice, room.id, 'accepted', [ids[0]]).status_code == 400  # expired

    @pytest.mark.parametrize('action,ids', [
        ('liked', ['a' * 64]), ('accepted', []), ('accepted', ['a' * 64, 'b' * 64]), ('dismissed', ['A' * 64]),
        ('dismissed', ['a' * 63]), ('dismissed', 'a' * 64), ('dismissed', ['a' * 64] * 4), ('dismissed', [1]),
    ])
    def test_rejects_malformed_feedback(self, alice, room, action, ids):
        assert feedback(alice, room.id, action, ids).status_code == 400


# ── Metrics and export ───────────────────────────────────────────────────────

def test_reply_metrics_prints_acceptance_per_variant(alice, bob, room):
    def shown(user, anchor, variant, *hashes):
        for h in hashes:
            ReplySuggestionEvent.objects.create(user=user, room=room, suggestion_hash=h, action='shown',
                                                variant=variant, anchor_message_id=anchor)

    shown(alice, 1, 'haiku', 'a', 'b')
    shown(alice, 2, 'haiku', 'c')
    shown(bob, 1, 'luna', 'd')
    ReplySuggestionEvent.objects.create(user=alice, room=room, suggestion_hash='a', action='accepted',
                                        variant='haiku', anchor_message_id=1)
    out = io.StringIO()
    call_command('reply_metrics', stdout=out)
    lines = {line.split()[0]: line.split() for line in out.getvalue().splitlines()[1:]}
    assert lines['haiku'][1:3] == ['2', '1'] and lines['haiku'][5] == '50.0%'
    assert lines['luna'][1:3] == ['1', '0'] and lines['luna'][5] == '0.0%'


class TestExportReplySft:
    def test_exports_only_all_seed_rooms_pseudonymised(self, tmp_path, alice, settings, ai_on):
        s1, s2 = _seed_user('demo1', 'Thandi'), _seed_user('demo2', 'Sipho')
        seed_room = make_room(s1, s2)
        Message.objects.create(room=seed_room, sender=s1, content='Hi Sipho, braai at 2?')
        Message.objects.create(room=seed_room, sender=s2, content='Lekker, see you @demo1')
        mixed = make_room(s1, alice)  # one real member: never exported or captured
        Message.objects.create(room=mixed, sender=alice, content='real user text')
        Message.objects.create(room=mixed, sender=s1, content='seed text in a mixed room')
        opted = _seed_user('demo3', 'Naledi', ai_opt_out=True)
        opted_room = make_room(s1, opted)
        Message.objects.create(room=opted_room, sender=opted, content='opted out text')
        Message.objects.create(room=opted_room, sender=s1, content='reply')

        settings.REPLY_SFT_CAPTURE_SEED_TEXT = True
        with ai_replies():
            ids = [s['id'] for s in suggest(s1, seed_room.id).data['suggestions']]
        with ai_replies(['a private reply']) as call:
            assert suggest(alice, mixed.id).status_code == 200
            assert suggest(s1, mixed.id).status_code == 200
        assert call.call_count == 2
        feedback(s1, seed_room.id, 'accepted', [ids[1]])
        # Text is captured for the all-seed room only.
        assert set(SeedReplySuggestion.objects.values_list('text', flat=True)) == set(SUGGESTIONS)

        out = tmp_path / 'conv.jsonl'
        call_command('export_reply_sft', out=str(out), stdout=io.StringIO())
        rows = [json.loads(line) for line in out.read_text(encoding='utf-8').splitlines()]
        assert len(rows) == 1
        dump = json.dumps(rows)
        for leaked in ('real user text', 'opted out text', 'Sipho', 'Thandi', 'demo1', 'example.test'):
            assert leaked not in dump
        assert [m['speaker'] for m in rows[0]['messages']] == ['Person 1', 'Person 2']
        assert rows[0]['messages'][0]['text'] == 'Hi Person 2, braai at 2?'
        assert rows[0]['messages'][1]['text'] == 'Lekker, see you Person 1'
        (sset,) = rows[0]['suggestion_sets']
        assert sset['viewer'] == 'Person 1' and sset['anchor'] == 1
        assert [s['action'] for s in sset['shown']] == ['ignored', 'accepted', 'ignored']
        assert [s['text'] for s in sset['shown']] == SUGGESTIONS

    def test_capture_is_off_by_default(self, db, ai_on):
        s1, s2 = _seed_user('demo1', 'Thandi'), _seed_user('demo2', 'Sipho')
        r = make_room(s1, s2)
        Message.objects.create(room=r, sender=s2, content='hi')
        with ai_replies():
            suggest(s1, r.id)
        assert not SeedReplySuggestion.objects.exists()


def _seed_user(username, first_name, **extra):
    from django.contrib.auth import get_user_model
    return get_user_model().objects.create_user(username=username, email=f'{username}@example.test',
                                                password='x-seed-password-123', first_name=first_name, **extra)
