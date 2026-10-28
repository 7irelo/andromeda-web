import io

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command

from watch import tasks
from watch.models import Video

User = get_user_model()


@pytest.fixture
def queued(monkeypatch):
    calls = []
    monkeypatch.setattr(tasks.process_video, 'delay', calls.append)
    return calls


def _legacy(user, name, is_public, **kw):
    key = default_storage.save(f'public/posts/videos/{name}', ContentFile(b'\x00\x00\x00\x18ftypmp42'))
    return Video.objects.create(uploader=user, title=name, video_file=key, is_public=is_public,
                                status=Video.STATUS_READY, **kw)


@pytest.fixture
def user(db):
    return User.objects.create_user(username='ana', password='pass-1234567', email='ana@example.com')


def test_reprocesses_legacy_videos_and_hides_private_originals(user, queued, django_capture_on_commit_callbacks):
    private = _legacy(user, 'private.mp4', is_public=False)
    public = _legacy(user, 'public.mp4', is_public=True)
    old_private = private.video_file.name
    modern = Video.objects.create(uploader=user, title='hls', video_file='private/watch/originals/x.mp4',
                                  status=Video.STATUS_READY, asset_id='abc', asset_files=['master.m3u8'])

    with django_capture_on_commit_callbacks(execute=True):
        call_command('reprocess_videos', stdout=io.StringIO())

    private.refresh_from_db()
    public.refresh_from_db()
    assert private.video_file.name.startswith('private/watch/originals/legacy/')
    assert default_storage.exists(private.video_file.name) and not default_storage.exists(old_private)
    assert public.video_file.name.startswith('public/')  # stays playable until processed
    assert {private.status, public.status} == {Video.STATUS_PROCESSING}
    assert sorted(queued) == sorted([private.pk, public.pk])
    modern.refresh_from_db()
    assert modern.status == Video.STATUS_READY


def test_dry_run_changes_nothing(user, queued):
    video = _legacy(user, 'dry.mp4', is_public=False)
    call_command('reprocess_videos', '--dry-run', stdout=io.StringIO())
    video.refresh_from_db()
    assert video.video_file.name.startswith('public/') and video.status == Video.STATUS_READY
    assert queued == []


def test_move_public_takes_processed_originals_private(user, queued, django_capture_on_commit_callbacks):
    video = _legacy(user, 'done.mp4', is_public=True, asset_id='abc', asset_files=['master.m3u8'])
    with django_capture_on_commit_callbacks(execute=True):
        call_command('reprocess_videos', '--move-public', stdout=io.StringIO())
    video.refresh_from_db()
    assert video.video_file.name.startswith('private/watch/originals/legacy/')
    assert queued == []
