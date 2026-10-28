"""Reports, staff actions, appeals, suspensions, data export and erasure."""
import io
import json
import zipfile
from datetime import timedelta

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone
from rest_framework.test import APIClient

from chats.models import ChatMember, ChatRoom, Message
from core.test_security import PASSWORD, befriend, client_for, make_user
from notifications.models import Notification
from posts.models import Post
from users.models import ConsentRecord, DataExport, User

from .models import Appeal, ModerationAction, ModerationCase, Report


@pytest.fixture
def people(db):
    staff = make_user('mod', is_staff=True)
    return make_user('alice'), make_user('bob'), make_user('mallory'), staff


def report(client, ctype, oid, reason='spam'):
    return client.post('/api/moderation/reports/', {'content_type': ctype, 'object_id': oid, 'reason': reason},
                       format='json')


class TestReporting:
    def test_can_only_report_what_you_can_see(self, people):
        alice, bob, mallory, _ = people
        secret = Post.objects.create(author=alice, content='friends only', privacy=Post.PRIVACY_FRIENDS)
        assert report(client_for(mallory), 'post', secret.id).status_code == 404
        befriend(alice, bob)
        assert report(client_for(bob), 'post', secret.id).status_code == 201

    def test_reports_of_one_item_share_one_case_and_count(self, people):
        alice, bob, mallory, _ = people
        p = Post.objects.create(author=alice, content='buy followers now')
        report(client_for(bob), 'post', p.id)
        report(client_for(mallory), 'post', p.id, 'scam')
        case = ModerationCase.objects.get(content_type='post', object_id=p.id)
        assert case.report_count == 2 and case.source == 'report' and case.snapshot == 'buy followers now'
        assert report(client_for(bob), 'post', p.id).status_code == 400  # one report per member

    def test_cannot_report_yourself_and_reasons_are_validated(self, people):
        alice = people[0]
        p = Post.objects.create(author=alice, content='x')
        assert report(client_for(alice), 'post', p.id).status_code == 400
        assert report(client_for(people[1]), 'post', p.id, 'made-up').status_code == 400

    def test_messages_only_reportable_by_room_members(self, people):
        alice, bob, mallory, _ = people
        room = ChatRoom.objects.create(room_type='direct', created_by=alice)
        ChatMember.objects.bulk_create([ChatMember(room=room, user=alice), ChatMember(room=room, user=bob)])
        m = Message.objects.create(room=room, sender=alice, content='threat')
        assert report(client_for(mallory), 'message', m.id).status_code == 404
        assert report(client_for(bob), 'message', m.id, 'harassment').status_code == 201

    def test_queue_is_staff_only(self, people):
        alice, bob, _, staff = people
        p = Post.objects.create(author=alice, content='x')
        report(client_for(bob), 'post', p.id)
        assert client_for(bob).get('/api/moderation/cases/').status_code == 403
        assert client_for(staff).get('/api/moderation/cases/').json()['count'] == 1


class TestActions:
    def _case(self, author, reporter):
        p = Post.objects.create(author=author, content='spam spam')
        report(client_for(reporter), 'post', p.id)
        return p, ModerationCase.objects.get(object_id=p.id)

    def test_remove_hides_content_tells_author_and_reporters_and_is_audited(self, people):
        alice, bob, _, staff = people
        p, case = self._case(alice, bob)
        r = client_for(staff).post(f'/api/moderation/cases/{case.id}/resolve/', {'action': 'remove'}, format='json')
        assert r.status_code == 200
        p.refresh_from_db()
        assert p.moderation_status == 'removed'
        assert ModerationAction.objects.filter(case=case, action='remove', moderator=staff).exists()
        assert Report.objects.get(case=case).status == 'actioned'
        assert Notification.objects.filter(recipient=alice, extra__case_id=case.id).exists()
        reporter_note = Notification.objects.get(recipient=bob)
        assert 'reviewed' in reporter_note.title and 'alice' not in reporter_note.title

    def test_staff_cannot_moderate_themselves(self, people):
        _, bob, _, staff = people
        _, case = self._case(staff, bob)
        r = client_for(staff).post(f'/api/moderation/cases/{case.id}/resolve/', {'action': 'approve'}, format='json')
        assert r.status_code == 403

    def test_suspension_blocks_sign_in_and_existing_tokens(self, people):
        alice, bob, _, staff = people
        _, case = self._case(alice, bob)
        c = APIClient()
        r = c.post('/api/auth/login/', {'username': 'alice', 'password': PASSWORD}, format='json')
        access = r.json()['access']
        client_for(staff).post(f'/api/moderation/cases/{case.id}/resolve/', {'action': 'suspend', 'days': 3},
                               format='json')
        c.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        assert c.get('/api/auth/me/').status_code == 401
        assert c.post('/api/auth/token/refresh/').status_code == 401
        r = APIClient().post('/api/auth/login/', {'username': 'alice', 'password': PASSWORD}, format='json')
        assert r.status_code == 400 and 'suspended' in str(r.json())

    def test_suspension_length_is_bounded(self, people):
        alice, bob, _, staff = people
        _, case = self._case(alice, bob)
        r = client_for(staff).post(f'/api/moderation/cases/{case.id}/resolve/', {'action': 'suspend', 'days': 999},
                                   format='json')
        assert r.status_code == 400

    def test_ban_deactivates(self, people):
        alice, bob, _, staff = people
        _, case = self._case(alice, bob)
        client_for(staff).post(f'/api/moderation/cases/{case.id}/resolve/', {'action': 'ban'}, format='json')
        alice.refresh_from_db()
        assert not alice.is_active

    def test_only_superusers_can_ban_staff(self, people):
        _, bob, _, staff = people
        other_staff = make_user('mod2', is_staff=True)
        _, case = self._case(other_staff, bob)
        r = client_for(staff).post(f'/api/moderation/cases/{case.id}/resolve/', {'action': 'ban'}, format='json')
        assert r.status_code == 403


class TestAppeals:
    def test_author_appeals_once_and_a_moderator_can_restore(self, people):
        alice, bob, mallory, staff = people
        p = Post.objects.create(author=alice, content='it was satire')
        report(client_for(bob), 'post', p.id)
        case = ModerationCase.objects.get(object_id=p.id)
        client_for(staff).post(f'/api/moderation/cases/{case.id}/resolve/', {'action': 'remove'}, format='json')
        assert client_for(mallory).post(f'/api/moderation/mine/{case.id}/appeal/', {}).status_code == 404
        mine = client_for(alice).get('/api/moderation/mine/').json()
        assert [c['id'] for c in mine] == [case.id]
        assert client_for(alice).post(f'/api/moderation/mine/{case.id}/appeal/',
                                      {'message': 'satire'}, format='json').status_code == 201
        assert client_for(alice).post(f'/api/moderation/mine/{case.id}/appeal/', {}).status_code == 400
        queue = client_for(staff).get('/api/moderation/cases/?appeals=true').json()
        assert queue['count'] == 1
        r = client_for(staff).post(f'/api/moderation/cases/{case.id}/appeal/', {'restore': True}, format='json')
        assert r.status_code == 200
        p.refresh_from_db()
        assert p.moderation_status == 'ok' and Appeal.objects.get(case=case).status == 'restored'

    def test_only_removals_can_be_appealed(self, people):
        alice, bob, _, staff = people
        p = Post.objects.create(author=alice, content='fine')
        report(client_for(bob), 'post', p.id)
        case = ModerationCase.objects.get(object_id=p.id)
        client_for(staff).post(f'/api/moderation/cases/{case.id}/resolve/', {'action': 'approve'}, format='json')
        assert client_for(alice).post(f'/api/moderation/mine/{case.id}/appeal/', {}).status_code == 400


class TestDataRights:
    @pytest.mark.django_db(transaction=True)
    def test_export_contains_own_data_only_and_downloads_only_for_owner(self):
        alice, bob = make_user('alice'), make_user('bob')
        Post.objects.create(author=alice, content='alice post')
        Post.objects.create(author=bob, content='bob post')
        c = client_for(alice)
        assert c.post('/api/auth/me/exports/').status_code == 202
        export = DataExport.objects.get(user=alice)
        assert export.status == 'ready'  # Celery runs eagerly in tests
        r = c.get(f'/api/auth/me/exports/{export.id}/download/')
        assert r.status_code == 200 and r['Cache-Control'] == 'private, no-store'
        z = zipfile.ZipFile(io.BytesIO(b''.join(r.streaming_content)))
        posts = json.loads(z.read('posts.json'))
        assert [p['content'] for p in posts] == ['alice post']
        assert json.loads(z.read('profile.json'))['email'] == 'alice@example.com'
        assert client_for(bob).get(f'/api/auth/me/exports/{export.id}/download/').status_code == 404

    def test_expired_exports_are_deleted(self, people):
        from users.tasks import expire_data_exports
        alice = people[0]
        e = DataExport.objects.create(user=alice, status='ready', expires_at=timezone.now() - timedelta(days=1))
        e.file.save('x.zip', ContentFile(b'zip'), save=True)
        assert expire_data_exports() == 1 and not DataExport.objects.exists()

    @pytest.mark.django_db(transaction=True)
    def test_deletion_is_delayed_cancellable_and_then_erases(self):
        from users.tasks import erase_due_accounts
        alice = make_user('alice')
        Post.objects.create(author=alice, content='goodbye')
        c = client_for(alice)
        assert c.post('/api/auth/me/delete/', {'password': PASSWORD}, format='json').status_code == 202
        # Signing in during the grace period cancels it.
        r = APIClient().post('/api/auth/login/', {'username': 'alice', 'password': PASSWORD}, format='json')
        assert r.status_code == 200
        alice.refresh_from_db()
        assert alice.deletion_scheduled_at is None
        User.objects.filter(pk=alice.pk).update(deletion_scheduled_at=timezone.now() - timedelta(minutes=1))
        assert erase_due_accounts() == 1
        assert not User.objects.filter(pk=alice.pk).exists() and not Post.objects.exists()

    @pytest.mark.django_db(transaction=True)
    def test_registration_requires_and_records_consent(self):
        body = {'username': 'zed', 'email': 'zed@example.com', 'first_name': 'Z', 'last_name': 'D',
                'password': PASSWORD, 'password2': PASSWORD}
        assert APIClient().post('/api/auth/register/', body, format='json').status_code == 400
        r = APIClient().post('/api/auth/register/', {**body, 'accept_terms': True}, format='json')
        assert r.status_code == 201
        kinds = set(ConsentRecord.objects.filter(user__username='zed').values_list('kind', flat=True))
        assert kinds == {'terms', 'privacy'}

    @pytest.mark.django_db(transaction=True)
    def test_deleting_rows_deletes_their_files(self):
        from django.core.files.storage import default_storage
        alice = make_user('alice')
        e = DataExport.objects.create(user=alice)
        e.file.save('x.zip', ContentFile(b'zip'), save=True)
        name = e.file.name
        assert default_storage.exists(name)
        e.delete()
        assert not default_storage.exists(name)
