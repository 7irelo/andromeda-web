"""Voice notes: upload, private playback, and the transcription task."""
import base64
from unittest import mock

import pytest
from celery.exceptions import Retry
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from chats.models import ChatMember, Message
from chats.tasks import TRANSCRIBE_MAX_RETRIES, transcribe_voice_note
from chats.tests.helpers import client_for, make_room, make_user, webm
from core import ai_client
from users.models import Block

pytestmark = pytest.mark.django_db


@pytest.fixture
def ai_on(settings):
    settings.AI_SERVICE_URL = 'http://ai.internal'
    settings.AI_SERVICE_SECRET = 'x' * 40


@pytest.fixture
def alice(db):
    return make_user('alice')


@pytest.fixture
def bob(db):
    return make_user('bob')


@pytest.fixture
def mallory(db):
    return make_user('mallory')


@pytest.fixture
def group(alice, bob):
    return make_room(alice, bob)


def recording(seconds=8, name='rec.webm'):
    return SimpleUploadedFile(name, webm(seconds), content_type='audio/webm')


def send_voice(user, room, upload=None):
    return client_for(user).post(reverse('message-list'), {
        'room': room.id, 'message_type': 'voice', 'file': upload or recording(),
    }, format='multipart')


def voice_message(room, sender, transcript_status='pending'):
    return Message.objects.create(room=room, sender=sender, message_type='voice', duration_s=8,
                                  transcript_status=transcript_status,
                                  file=SimpleUploadedFile('voice.webm', webm(8)))


class TestUpload:
    def test_member_uploads_voice_note(self, group, alice, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks() as callbacks:
            r = send_voice(alice, group, recording(name='../../evil.exe'))
        assert r.status_code == 201, r.data
        msg = Message.objects.get(pk=r.data['id'])
        assert msg.message_type == 'voice' and msg.duration_s == pytest.approx(8)
        assert msg.file.name.startswith('private/chat_files/') and msg.file.name.endswith('.webm')
        assert r.data['file_url'].endswith(f'/api/chats/messages/{msg.id}/file/')
        # AI service not configured: no transcript is expected, and none is queued.
        assert msg.transcript_status == ''
        with mock.patch('chats.tasks.transcribe_voice_note.apply_async') as queued:
            for cb in callbacks:
                cb()
        queued.assert_not_called()

    def test_transcription_queued_on_commit(self, group, alice, ai_on, django_capture_on_commit_callbacks):
        with mock.patch('chats.tasks.transcribe_voice_note.apply_async') as queued:
            with django_capture_on_commit_callbacks() as callbacks:
                r = send_voice(alice, group)
            queued.assert_not_called()  # nothing runs before the transaction commits
            for cb in callbacks:
                cb()
        queued.assert_called_once_with(args=[r.data['id']], queue='messages')
        assert r.data['transcript_status'] == 'pending'

    def test_non_member_cannot_upload(self, group, mallory):
        assert send_voice(mallory, group).status_code == 403
        assert not Message.objects.exists()

    def test_blocked_dm_cannot_upload(self, alice, bob):
        dm = make_room(alice, bob, room_type='direct')
        Block.objects.create(blocker=bob, blocked=alice)
        assert send_voice(alice, dm).status_code == 403

    def test_rejects_non_audio_and_missing_file(self, group, alice):
        fake = SimpleUploadedFile('rec.webm', b'<html>hi</html>', content_type='audio/webm')
        assert send_voice(alice, group, fake).status_code == 400
        r = client_for(alice).post(reverse('message-list'), {'room': group.id, 'message_type': 'voice'})
        assert r.status_code == 400
        too_long = SimpleUploadedFile('rec.webm', webm(400), content_type='audio/webm')
        assert send_voice(alice, group, too_long).status_code == 400
        assert not Message.objects.exists()


class TestPlayback:
    def test_members_only(self, group, alice, bob, mallory):
        msg = voice_message(group, alice)
        file_url = reverse('message-file', kwargs={'pk': msg.pk})
        r = client_for(bob).get(file_url)
        assert r.status_code == 200
        assert r['Content-Type'] == 'audio/webm'
        assert r['Cache-Control'] == 'private, no-store' and r['X-Content-Type-Options'] == 'nosniff'
        assert client_for(mallory).get(file_url).status_code == 404

    def test_removed_member_loses_access(self, group, alice, bob):
        msg = voice_message(group, alice)
        ChatMember.objects.filter(room=group, user=bob).delete()
        assert client_for(bob).get(reverse('message-file', kwargs={'pk': msg.pk})).status_code == 404

    def test_deleted_voice_note_removes_file(self, group, alice):
        msg = voice_message(group, alice)
        storage, name = msg.file.storage, msg.file.name
        assert client_for(alice).delete(reverse('message-detail', kwargs={'pk': msg.pk})).status_code == 204
        assert not storage.exists(name)
        assert client_for(alice).get(reverse('message-file', kwargs={'pk': msg.pk})).status_code == 404


@pytest.mark.usefixtures('ai_on')
class TestTranscription:
    def test_stores_transcript_and_pushes_update(self, group, alice):
        msg = voice_message(group, alice)
        with mock.patch('core.ai_client.call', return_value={'transcript': ' See you at six ', 'language': 'en',
                                                             'duration_s': 8.0}) as call, \
                mock.patch('chats.services.broadcast') as broadcast:
            assert transcribe_voice_note(msg.id) == 'done'
        path, payload = call.call_args.args
        assert path == '/v1/transcribe' and call.call_args.kwargs == {'user_id': alice.id}
        assert payload['mimetype'] == 'audio/webm' and payload['purpose'] == 'voice_note'
        assert base64.b64decode(payload['audio_b64']) == webm(8)
        msg.refresh_from_db()
        assert msg.transcript == 'See you at six' and msg.transcript_status == 'done'
        room_id, event = broadcast.call_args.args
        assert room_id == group.id and event['type'] == 'message_updated'
        assert event['message']['transcript'] == 'See you at six'

    def test_idempotent(self, group, alice):
        msg = voice_message(group, alice)
        with mock.patch('core.ai_client.call', return_value={'transcript': 'hi'}) as call:
            transcribe_voice_note(msg.id)
            transcribe_voice_note(msg.id)
        assert call.call_count == 1

    def test_skips_deleted_and_non_voice(self, group, alice):
        deleted = voice_message(group, alice)
        Message.objects.filter(pk=deleted.pk).update(is_deleted=True)
        text = Message.objects.create(room=group, sender=alice, content='hello')
        with mock.patch('core.ai_client.call') as call:
            assert transcribe_voice_note(deleted.id) is None
            assert transcribe_voice_note(text.id) is None
            assert transcribe_voice_note(987654) is None
        call.assert_not_called()

    def test_rejected_leaves_voice_note_without_transcript(self, group, alice):
        msg = voice_message(group, alice)
        with mock.patch('core.ai_client.call', side_effect=ai_client.AIRejected(429, 'Daily audio allowance used up')):
            assert transcribe_voice_note(msg.id) == 'failed'
        msg.refresh_from_db()
        assert msg.transcript == '' and msg.transcript_status == 'failed'

    def test_unavailable_is_retried(self, group, alice):
        msg = voice_message(group, alice)
        with mock.patch('core.ai_client.call', side_effect=ai_client.AIUnavailable('down')):
            with pytest.raises(Retry):
                transcribe_voice_note.apply(args=[msg.id], throw=True)
        msg.refresh_from_db()
        assert msg.transcript_status == 'pending'

    def test_unavailable_gives_up_after_last_retry(self, group, alice):
        msg = voice_message(group, alice)
        with mock.patch('core.ai_client.call', side_effect=ai_client.AIUnavailable('down')) as call:
            result = transcribe_voice_note.apply(args=[msg.id], retries=TRANSCRIBE_MAX_RETRIES)
        assert call.call_count == 1 and result.get() == 'failed'
        msg.refresh_from_db()
        assert msg.transcript_status == 'failed' and msg.transcript == ''

    def test_transcript_is_searchable(self, group, alice, bob):
        msg = voice_message(group, alice)
        with mock.patch('core.ai_client.call', return_value={'transcript': 'the spare key is under the mat'}):
            transcribe_voice_note(msg.id)
        r = client_for(bob).get(reverse('chatroom-search', kwargs={'pk': group.pk}) + '?q=spare key')
        assert [m['id'] for m in r.data['results']] == [msg.id]
        assert r.data['results'][0]['transcript'] == 'the spare key is under the mat'


def test_ai_not_configured_marks_failed(group, alice):
    msg = voice_message(group, alice)
    with mock.patch('core.ai_client.call') as call:
        assert transcribe_voice_note(msg.id) == 'failed'
    call.assert_not_called()
