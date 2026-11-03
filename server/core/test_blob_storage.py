"""Blob storage, public media serving and the scheduled-task endpoint, with a fake Blob SDK."""
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import mock

import pytest
from celery.schedules import crontab
from django.core.files.base import ContentFile
from django.test import override_settings
from django.urls import path
from rest_framework.test import APIClient

from core import blob_storage, media_views


class FakeBlob:
    def __init__(self):
        self.files = {}

    def put_blob(self, name, body, access, content_type=None):
        assert access == 'private'
        self.files[name] = body

    def get_blob(self, name, access):
        assert access == 'private'
        if name not in self.files:
            raise FileNotFoundError(name)
        return SimpleNamespace(body=self.files[name])

    def head_blob(self, name):
        if name not in self.files:
            raise FileNotFoundError(name)
        return SimpleNamespace(size=len(self.files[name]), uploaded_at=datetime(2026, 1, 1, tzinfo=UTC))

    def delete_blob(self, name):
        self.files.pop(name, None)


urlpatterns = [
    path('media/<path:path>', media_views.public_media),
    path('api/internal/cron/', media_views.run_scheduled_tasks),
]


@pytest.fixture
def blob(monkeypatch):
    fake = FakeBlob()
    monkeypatch.setattr(blob_storage, '_sdk', lambda: fake)
    monkeypatch.setattr(media_views, 'default_storage', blob_storage.BlobStorage())
    return fake


def test_round_trip_exists_size_delete(blob):
    storage = blob_storage.BlobStorage()
    name = storage.save('public/avatars/abc.png', ContentFile(b'data'))
    assert name == 'public/avatars/abc.png' and storage.exists(name) and storage.size(name) == 4
    assert storage.open(name).read() == b'data'
    assert storage.url('public/a b.png') == '/media/public/a%20b.png'
    storage.delete(name)
    assert not storage.exists(name)


@override_settings(ROOT_URLCONF=__name__)
def test_public_media_is_served_with_a_locked_down_policy(blob):
    blob.files['public/a.png'] = b'img'
    response = APIClient().get('/media/public/a.png')
    assert response.status_code == 200 and response.content == b'img' and response['Content-Type'] == 'image/png'
    assert 'sandbox' in response['Content-Security-Policy'] and response['X-Content-Type-Options'] == 'nosniff'


@override_settings(ROOT_URLCONF=__name__)
@pytest.mark.parametrize('url', ['/media/private/chat_files/secret.pdf', '/media/public/../private/secret.pdf',
                                 '/media/public/missing.png'])
def test_private_traversal_and_missing_files_are_not_served(blob, url):
    blob.files['private/chat_files/secret.pdf'] = b'secret'
    blob.files['private/secret.pdf'] = b'secret'
    assert APIClient().get(url).status_code == 404


def test_due_today_respects_weekly_schedules():
    saturday = datetime(2026, 11, 7, tzinfo=UTC)
    sunday = datetime(2026, 11, 8, tzinfo=UTC)
    weekly = crontab(day_of_week='sat', hour=8, minute=0)
    assert media_views.due_today(weekly, saturday) and not media_views.due_today(weekly, sunday)
    assert media_views.due_today(crontab(hour=3, minute=0), sunday)
    assert media_views.due_today(60.0, sunday)


SCHEDULE = {'daily': {'task': 'a.daily', 'schedule': crontab(hour=3, minute=0)},
            'never_today': {'task': 'a.other', 'schedule': crontab(month_of_year=1, day_of_month=1)}}


@override_settings(ROOT_URLCONF=__name__, CRON_SECRET='s3cret', CELERY_BEAT_SCHEDULE={'daily': SCHEDULE['daily']})
def test_cron_requires_the_secret_then_sends_due_tasks():
    with mock.patch.object(media_views.current_app, 'send_task') as send:
        assert APIClient().get('/api/internal/cron/').status_code == 401
        assert APIClient().get('/api/internal/cron/', HTTP_AUTHORIZATION='Bearer wrong').status_code == 401
        send.assert_not_called()
        response = APIClient().get('/api/internal/cron/', HTTP_AUTHORIZATION='Bearer s3cret')
    assert response.status_code == 200 and response.json() == {'sent': ['daily']}
    send.assert_called_once_with('a.daily', args=(), kwargs={})


@override_settings(ROOT_URLCONF=__name__, CRON_SECRET='')
def test_cron_is_absent_without_a_secret():
    assert APIClient().get('/api/internal/cron/').status_code == 404
