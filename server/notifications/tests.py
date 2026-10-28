"""Notification preferences, grouping, blocking and Web Push subscriptions."""
from unittest import mock

import pytest
from django.core import mail
from django.test import override_settings
from rest_framework.test import APIClient

from core.test_security import make_user
from users.models import Block

from .models import Notification, NotificationPreference, PushSubscription
from .service import notify
from . import tasks


@pytest.fixture
def people(db):
    return make_user('alice'), make_user('bob'), make_user('carol'), make_user('dave')


def test_repeat_likes_fold_into_one_notification(people):
    alice, bob, carol, dave = people
    for liker in (bob, carol, dave):
        tasks.send_like_notification(liker.id, alice.id, 7)
    rows = Notification.objects.filter(recipient=alice)
    assert rows.count() == 1
    n = rows.get()
    assert n.extra['count'] == 3 and n.title == 'dave and 2 others liked your post'


def test_read_notifications_are_not_reused_for_grouping(people):
    alice, bob, carol, _ = people
    tasks.send_like_notification(bob.id, alice.id, 7)
    Notification.objects.update(is_read=True)
    tasks.send_like_notification(carol.id, alice.id, 7)
    assert Notification.objects.filter(recipient=alice).count() == 2


def test_blocked_senders_never_notify_in_either_direction(people):
    alice, bob, carol, _ = people
    Block.objects.create(blocker=alice, blocked=bob)
    Block.objects.create(blocker=carol, blocked=alice)
    tasks.send_like_notification(bob.id, alice.id, 1)
    tasks.send_comment_notification(alice.id, carol.id, 2, 3)
    assert not Notification.objects.exists()


def test_no_self_notifications(people):
    alice = people[0]
    tasks.send_like_notification(alice.id, alice.id, 1)
    assert not Notification.objects.exists()


def test_preferences_turn_categories_off_but_not_safety_notices(people):
    alice, bob, _, _ = people
    c = APIClient()
    c.force_authenticate(alice)
    r = c.patch('/api/notifications/preferences/', {
        'categories': {'likes': {'in_app': False, 'push': False, 'email': False},
                       'account': {'in_app': False}}}, format='json')
    assert r.status_code == 200
    cats = {x['key']: x for x in r.json()['categories']}
    assert cats['likes']['in_app'] is False and cats['account']['in_app'] is True
    tasks.send_like_notification(bob.id, alice.id, 1)
    assert not Notification.objects.filter(recipient=alice).exists()
    notify(alice, Notification.TYPE_SYSTEM, 'Your post was removed', extra={'kind': 'moderation'})
    assert Notification.objects.filter(recipient=alice).count() == 1


def test_email_only_category_is_hidden_from_the_in_app_list(people):
    alice, bob, _, _ = people
    NotificationPreference.objects.create(user=alice, channels={'mentions': {'in_app': False, 'email': True}})
    notify(alice, Notification.TYPE_MENTION, 'bob mentioned you', sender=bob, extra={'post_id': 1})
    c = APIClient()
    c.force_authenticate(alice)
    assert c.get('/api/notifications/').json()['count'] == 0
    assert c.get('/api/notifications/unread-count/').json()['unread_count'] == 0


@pytest.mark.django_db(transaction=True)
def test_mentions_email_immediately_and_digest_covers_the_rest():
    alice, bob = make_user('alice'), make_user('bob')
    notify(alice, Notification.TYPE_MENTION, 'bob mentioned you', sender=bob, extra={'post_id': 1})
    assert len(mail.outbox) == 1 and 'bob mentioned you' in mail.outbox[0].subject
    tasks.send_comment_notification(bob.id, alice.id, 1, 2)
    assert tasks.send_daily_digests() == 1
    assert 'commented on your post' in mail.outbox[-1].body
    assert tasks.send_daily_digests() == 0  # nothing is emailed twice


def test_digest_respects_opt_out(people):
    alice, bob, _, _ = people
    NotificationPreference.objects.create(user=alice, email_digest='off')
    tasks.send_comment_notification(bob.id, alice.id, 1, 2)
    assert tasks.send_daily_digests() == 0


def test_listing_digest_is_opt_in_and_skips_blocked_sellers(people):
    from marketplace.models import Listing
    alice, bob, carol, _ = people
    alice.location = 'Durban'
    alice.save()
    Listing.objects.create(seller=bob, title='Couch', description='x', price=10, location='Durban')
    Listing.objects.create(seller=carol, title='Lamp', description='x', price=5, location='Durban')
    assert tasks.send_listing_digests() == 0
    NotificationPreference.objects.create(user=alice, listing_digest=True)
    Block.objects.create(blocker=alice, blocked=carol)
    assert tasks.send_listing_digests() == 1
    n = Notification.objects.get(recipient=alice)
    assert len(n.extra['listing_ids']) == 1 and n.title.startswith('1 new listing near Durban')


class TestPushSubscriptions:
    def test_only_known_https_push_services_are_accepted(self, people):
        c = APIClient()
        c.force_authenticate(people[0])
        keys = {'p256dh': 'BPub', 'auth': 'secret'}
        for bad in ('http://fcm.googleapis.com/x', 'https://169.254.169.254/latest', 'https://evil.example/push',
                    'https://fcm.googleapis.com.evil.example/x'):
            assert c.post('/api/notifications/push/', {'endpoint': bad, 'keys': keys}, format='json').status_code == 400
        ok = c.post('/api/notifications/push/', {'endpoint': 'https://fcm.googleapis.com/fcm/send/abc',
                                                  'keys': keys}, format='json')
        assert ok.status_code == 201 and PushSubscription.objects.count() == 1

    def test_users_only_remove_their_own_subscriptions(self, people):
        alice, bob, _, _ = people
        PushSubscription.objects.create(user=alice, endpoint='https://fcm.googleapis.com/a', p256dh='k', auth='a')
        c = APIClient()
        c.force_authenticate(bob)
        c.delete('/api/notifications/push/', {'endpoint': 'https://fcm.googleapis.com/a'}, format='json')
        assert PushSubscription.objects.count() == 1

    @override_settings(VAPID_PUBLIC_KEY='pub', VAPID_PRIVATE_KEY='priv')
    def test_gone_subscriptions_are_pruned(self, people):
        from pywebpush import WebPushException
        alice = people[0]
        PushSubscription.objects.create(user=alice, endpoint='https://fcm.googleapis.com/a', p256dh='k', auth='a')
        gone = WebPushException('gone', response=mock.Mock(status_code=410))
        with mock.patch('pywebpush.webpush', side_effect=gone):
            assert tasks.deliver_web_push(alice.id, 't', 'b') == 0
        assert not PushSubscription.objects.exists()

    def test_public_key_hidden_when_push_not_configured(self, people):
        c = APIClient()
        c.force_authenticate(people[0])
        assert c.get('/api/notifications/push/').json() == {'public_key': None}


def test_websocket_event_keeps_the_consumer_handler_name(people, monkeypatch):
    sent = []

    class Layer:
        async def group_send(self, group, event):
            sent.append((group, event))
    monkeypatch.setattr('notifications.service.get_channel_layer', lambda: Layer())
    from .service import push_websocket
    push_websocket(5, {'type': 'like', 'id': 1})
    assert sent == [('notifications_5', {'type': 'send_notification', 'id': 1})]
