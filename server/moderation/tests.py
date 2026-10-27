from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from chats.models import ChatMember, ChatRoom, Message
from marketplace.models import Listing
from moderation.models import ModerationAction, ModerationCase
from moderation.tasks import moderate_content
from posts.models import Post
from users.models import Block

User = get_user_model()


def client_for(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture
def alice(db):
    return User.objects.create_user('alice', 'alice@example.com', 'correct-horse-battery')


@pytest.fixture
def bob(db):
    return User.objects.create_user('bob', 'bob@example.com', 'correct-horse-battery')


@pytest.fixture
def staff(db):
    return User.objects.create_user('mod', 'mod@example.com', 'correct-horse-battery', is_staff=True)


def ai_says(decision, **extra):
    return mock.patch('core.ai_client.call', return_value={
        'decision': decision, 'categories': ['scam'] if decision != 'allow' else [], 'confidence': 0.9,
        'reason': 'test', 'model': 'claude-haiku-5-5', 'stages': ['claude-haiku-5-5'], 'cost_usd': 0.0001, **extra})


class TestModerationPipeline:
    def test_removed_post_hidden_from_others_but_not_author(self, alice, bob):
        post = Post.objects.create(author=alice, content='Pay a deposit first')
        with ai_says('remove'):
            moderate_content('post', post.id)
        post.refresh_from_db()
        assert post.moderation_status == 'removed'
        assert client_for(bob).get(reverse('post-detail', kwargs={'pk': post.pk})).status_code == 404
        mine = client_for(alice).get(reverse('post-detail', kwargs={'pk': post.pk}))
        assert mine.status_code == 200 and mine.data['moderation_status'] == 'removed'
        assert alice.notifications.filter(notification_type='system').exists()

    def test_review_keeps_content_visible_and_queues_case(self, alice, bob):
        post = Post.objects.create(author=alice, content='borderline')
        with ai_says('review'):
            moderate_content('post', post.id)
        assert client_for(bob).get(reverse('post-detail', kwargs={'pk': post.pk})).status_code == 200
        assert ModerationCase.objects.filter(object_id=post.id, resolved=False).exists()

    def test_removed_listing_hidden(self, alice, bob):
        listing = Listing.objects.create(seller=alice, title='Cheap phone', price=10)
        with ai_says('remove'):
            moderate_content('listing', listing.id)
        ids = [item['id'] for item in client_for(bob).get(reverse('listing-list')).data['results']]
        assert listing.id not in ids

    def test_cannot_set_moderation_status_via_api(self, alice):
        r = client_for(alice).post(reverse('post-list'), {'content': 'x', 'moderation_status': 'ok'})
        post = Post.objects.get(pk=r.data['id'])
        post.moderation_status = 'removed'
        post.save()
        client_for(alice).patch(reverse('post-detail', kwargs={'pk': post.pk}), {'moderation_status': 'ok'},
                                format='json')
        post.refresh_from_db()
        assert post.moderation_status == 'removed'


class TestReviewQueue:
    def test_staff_only(self, alice):
        assert client_for(alice).get(reverse('moderation-case-list')).status_code == 403

    def test_staff_restore_is_audited(self, alice, staff):
        post = Post.objects.create(author=alice, content='x', moderation_status='removed')
        case = ModerationCase.objects.create(content_type='post', object_id=post.id, author=alice, decision='remove')
        r = client_for(staff).post(reverse('moderation-case-resolve', kwargs={'pk': case.pk}),
                                   {'action': 'restore', 'note': 'False positive'})
        assert r.status_code == 200
        post.refresh_from_db()
        assert post.moderation_status == 'ok'
        assert ModerationAction.objects.get(case=case).moderator == staff


class TestCatchUp:
    @pytest.fixture
    def room(self, alice, bob):
        room = ChatRoom.objects.create(room_type='group', name='Braai crew', created_by=alice)
        ChatMember.objects.create(room=room, user=alice, role='admin')
        ChatMember.objects.create(room=room, user=bob)
        return room

    def test_non_member_cannot_summarise(self, room, db):
        outsider = User.objects.create_user('eve', 'eve@example.com', 'correct-horse-battery')
        assert client_for(outsider).post(reverse('chatroom-catch-up', kwargs={'pk': room.pk})).status_code == 404

    def test_sends_only_visible_messages_and_returns_summary(self, room, alice, bob):
        mallory = User.objects.create_user('mallory', 'm@example.com', 'correct-horse-battery')
        ChatMember.objects.create(room=room, user=mallory)
        Message.objects.create(room=room, sender=bob, content='Braai Saturday?')
        Message.objects.create(room=room, sender=mallory, content='spam spam')
        Block.objects.create(blocker=alice, blocked=mallory)
        summary = {'tldr': 'Braai on Saturday', 'topics': [], 'decisions': [], 'questions_for_you': []}
        with mock.patch('core.ai_client.call', return_value={'summary': summary}) as call:
            r = client_for(alice).post(reverse('chatroom-catch-up', kwargs={'pk': room.pk}))
        assert r.status_code == 200 and r.data['tldr'] == 'Braai on Saturday'
        sent = call.call_args.args[1]['messages']
        assert [m['sender'] for m in sent] == ['bob']
        assert call.call_args.kwargs['user_id'] == alice.id

    def test_unavailable_degrades(self, room, alice):
        Message.objects.create(room=room, sender=alice, content='hi')
        r = client_for(alice).post(reverse('chatroom-catch-up', kwargs={'pk': room.pk}))
        assert r.status_code == 503


def test_service_token_shape(settings):
    import jwt
    from core.ai_client import _token
    settings.AI_SERVICE_SECRET = 's' * 40
    claims = jwt.decode(_token(7), 's' * 40, algorithms=['HS256'], audience='andromeda-ai')
    assert claims['sub'] == '7' and claims['exp'] - claims['iat'] == 60 and claims['iss'] == 'andromeda-api'
