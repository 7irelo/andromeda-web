"""
Watch: the processing pipeline, captions, playback links, progress and channels.

ffmpeg never runs here: ``_exec`` is replaced by a fake that writes the files
ffmpeg would have written, and the AI service is a stub.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core import ai_client
from core.test_security import client_for, make_user
from notifications.models import Notification
from users.models import Block

from . import captions, ffmpeg, tasks
from .access import asset_key, audio_key, stream_token
from .models import ChannelSubscription, Video, VideoView, WatchProgress

MP4 = b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 64


class FakeFFmpeg:
    """Stands in for the ffmpeg/ffprobe binaries."""

    def __init__(self, width=1920, height=1080, duration=300.0, audio=True, format_name='mov,mp4,m4a,3gp,3g2,mj2',
                 fail_on=None):
        self.calls = []
        self.probe = {
            'format': {'format_name': format_name, 'duration': str(duration)},
            'streams': [{'codec_type': 'video', 'width': width, 'height': height}]
            + ([{'codec_type': 'audio'}] if audio else []),
        }
        self.fail_on = fail_on

    def __call__(self, argv, timeout):
        self.calls.append(argv)
        assert all(isinstance(a, str) for a in argv) and timeout > 0
        tool, out = argv[0], argv[-1]
        if self.fail_on and self.fail_on in out:
            return SimpleNamespace(returncode=1, stdout=b'', stderr=b'boom')
        if tool == 'ffprobe':
            return SimpleNamespace(returncode=0, stdout=json.dumps(self.probe).encode(), stderr=b'')
        if out.endswith('index.m3u8'):
            seg = argv[argv.index('-hls_segment_filename') + 1].replace('%05d', '00000')
            Path(seg).write_bytes(b'\x47' * 188)
            Path(out).write_text('#EXTM3U\n#EXTINF:6.0,\nseg_00000.ts\n#EXT-X-ENDLIST\n')
        else:
            Path(out).write_bytes(b'\xff\xd8 fake output')
        return SimpleNamespace(returncode=0, stdout=b'', stderr=b'')

    def outputs(self):
        return [Path(c[-1]).name for c in self.calls if c[0] == 'ffmpeg']


@pytest.fixture
def fake_ffmpeg(monkeypatch):
    fake = FakeFFmpeg()
    monkeypatch.setattr(ffmpeg, '_binary', lambda name: name)
    monkeypatch.setattr(ffmpeg, '_exec', fake)
    return fake


class FakeAI:
    def __init__(self, transcribe=None, chapters=None, error=None):
        self.calls, self.error = [], error
        self.transcribe = transcribe or {
            'transcript': 'Welcome to the braai. Now the fire.', 'language': 'en', 'duration_s': 300.0,
            'utterances': [{'start': 0.0, 'end': 4.0, 'speaker': 0, 'text': 'Welcome to the braai.'},
                           {'start': 150.0, 'end': 155.0, 'speaker': 0, 'text': 'Now the fire.'}],
            'paragraphs': [], 'vtt': 'WEBVTT\n\n00:00:00.000 --> 00:00:04.000\nWelcome to the braai.\n',
        }
        self.chapters = chapters if chapters is not None else {
            'chapters': [{'start_s': 3, 'title': 'Intro'}, {'start_s': 150, 'title': 'The fire'}]}

    def __call__(self, path, payload, user_id):
        self.calls.append((path, payload, user_id))
        if self.error:
            raise self.error
        return self.transcribe if path == '/v1/transcribe' else self.chapters


def make_video(user, **extra):
    extra.setdefault('title', 'Braai day')
    return Video.objects.create(uploader=user, video_file=SimpleUploadedFile('clip.mp4', MP4), **extra)


def process(video):
    tasks.process_video.apply(args=[video.pk])
    video.refresh_from_db()
    return video


@pytest.fixture
def alice(db):
    return make_user('alice')


@pytest.fixture
def bob(db):
    return make_user('bob')


# ── Pipeline ─────────────────────────────────────────────────────────────────

class TestPipeline:
    def test_public_video_becomes_ready_with_hls_thumbnail_and_sprite(self, alice, fake_ffmpeg,
                                                                       django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            video = process(make_video(alice))
        assert video.status == Video.STATUS_READY and video.failure_reason == ''
        assert (video.duration, video.width, video.height, video.renditions) == (300, 1920, 1080, [360, 720])
        assert video.asset_root == 'public'
        assert set(video.asset_files) == {'master.m3u8', 'thumb.jpg', 'sprite.jpg', '360p/index.m3u8',
                                          '360p/seg_00000.ts', '720p/index.m3u8', '720p/seg_00000.ts'}
        for rel in video.asset_files:
            assert default_storage.exists(asset_key(video, rel))
        master = default_storage.open(asset_key(video, 'master.m3u8')).read().decode()
        assert '360p/index.m3u8' in master and '720p/index.m3u8' in master and 'RESOLUTION=1280x720' in master
        # AI is off: no audio is extracted at all.
        assert 'audio.webm' not in fake_ffmpeg.outputs() and video.captions_status == Video.CAPTIONS_NONE
        assert video.processing_started_at is None

    def test_low_resolution_source_skips_720p(self, alice, fake_ffmpeg):
        fake_ffmpeg.probe['streams'][0].update(width=640, height=480)
        video = process(make_video(alice))
        assert video.renditions == [360] and not any(f.startswith('720p/') for f in video.asset_files)

    def test_portrait_video_keeps_its_shape(self, alice, fake_ffmpeg):
        fake_ffmpeg.probe['streams'][0].update(width=1080, height=1920)
        video = process(make_video(alice))
        master = default_storage.open(asset_key(video, 'master.m3u8')).read().decode()
        assert 'RESOLUTION=360x640' in master and 'RESOLUTION=720x1280' in master

    def test_too_long_fails_with_a_reason(self, alice, fake_ffmpeg):
        fake_ffmpeg.probe['format']['duration'] = str(21 * 60)
        video = process(make_video(alice))
        assert video.status == Video.STATUS_FAILED and '20 minutes' in video.failure_reason
        assert video.asset_files == [] and fake_ffmpeg.outputs() == []

    @pytest.mark.parametrize('format_name', ['hls', 'concat', 'image2', 'avi'])
    def test_only_mp4_and_webm_demuxers_accepted(self, alice, fake_ffmpeg, format_name):
        fake_ffmpeg.probe['format']['format_name'] = format_name
        video = process(make_video(alice))
        assert video.status == Video.STATUS_FAILED and 'MP4' in video.failure_reason

    def test_no_video_track_fails(self, alice, fake_ffmpeg):
        fake_ffmpeg.probe['streams'] = [{'codec_type': 'audio'}]
        assert process(make_video(alice)).failure_reason == 'This file has no video track.'

    def test_transcode_error_fails_and_cleans_up(self, alice, fake_ffmpeg):
        fake_ffmpeg.fail_on = '720p'
        video = process(make_video(alice))
        assert video.status == Video.STATUS_FAILED and video.failure_reason == "We couldn't process this video."
        assert not default_storage.exists(asset_key(video, 'thumb.jpg', 'public'))

    def test_sprite_failure_is_not_fatal(self, alice, fake_ffmpeg):
        fake_ffmpeg.fail_on = 'sprite.jpg'
        video = process(make_video(alice))
        assert video.status == Video.STATUS_READY and 'sprite.jpg' not in video.asset_files

    def test_ffmpeg_arguments_are_safe(self, alice, fake_ffmpeg, monkeypatch):
        video = make_video(alice, title='$(rm -rf /); `id` | -i http://evil/x.m3u8')
        process(video)
        for argv in fake_ffmpeg.calls:
            joined = ' '.join(argv)
            assert 'evil' not in joined and 'rm -rf' not in joined and 'clip' not in joined
            src = argv.index('-i') + 1 if '-i' in argv else len(argv) - 1  # ffprobe takes it last
            assert argv[argv.index('-protocol_whitelist') + 1] == 'file'
            assert argv.index('-format_whitelist') < src and Path(argv[src]).name == 'source'

    def test_timeout_fails_cleanly(self, alice, fake_ffmpeg, monkeypatch):
        import subprocess

        def slow(argv, timeout):
            raise subprocess.TimeoutExpired(argv, timeout)
        monkeypatch.setattr(ffmpeg, '_exec', slow)
        assert process(make_video(alice)).failure_reason == 'Processing this video took too long.'

    def test_is_idempotent(self, alice, fake_ffmpeg):
        video = process(make_video(alice))
        calls = len(fake_ffmpeg.calls)
        assert tasks.process_video.apply(args=[video.pk]).get() == 'skipped'
        assert len(fake_ffmpeg.calls) == calls

    def test_transient_errors_retry_then_fail(self, alice, fake_ffmpeg, monkeypatch):
        def broken(field, dest):
            raise OSError('storage down')
        monkeypatch.setattr(tasks, '_download', broken)
        video = make_video(alice)
        # Last attempt: give up with a user-visible reason.
        assert tasks.process_video.apply(args=[video.pk], retries=3).get() == 'failed'
        video.refresh_from_db()
        assert video.status == Video.STATUS_FAILED and 'try uploading again' in video.failure_reason

    def test_private_video_assets_are_private(self, alice, fake_ffmpeg):
        video = process(make_video(alice, is_public=False))
        assert video.asset_root == 'private'
        assert default_storage.exists(f'private/watch/hls/{video.asset_id}/master.m3u8')
        assert not default_storage.exists(f'public/watch/hls/{video.asset_id}/master.m3u8')

    def test_original_upload_is_stored_privately(self, alice):
        assert make_video(alice).video_file.name.startswith('private/watch/originals/')

    def test_custom_thumbnail_is_used(self, alice, fake_ffmpeg):
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new('RGB', (50, 30), 'red').save(buf, format='PNG')
        video = make_video(alice, thumbnail=SimpleUploadedFile('t.png', buf.getvalue()))
        video = process(video)
        assert 'thumb.jpg' not in fake_ffmpeg.outputs()
        assert Image.open(default_storage.open(asset_key(video, 'thumb.jpg'))).format == 'JPEG'

    def test_stuck_videos_are_requeued(self, alice, monkeypatch):
        from datetime import timedelta
        from django.utils import timezone
        queued = []
        monkeypatch.setattr(tasks.process_video, 'delay', queued.append)
        stuck = make_video(alice)
        Video.objects.filter(pk=stuck.pk).update(processing_started_at=timezone.now() - timedelta(hours=3))
        make_video(alice)  # fresh: left alone
        assert tasks.requeue_stuck_videos() == 1 and queued == [stuck.pk]


# ── Captions & chapters ──────────────────────────────────────────────────────

class TestCaptions:
    @pytest.fixture(autouse=True)
    def _ai_on(self, settings):
        settings.AI_SERVICE_URL, settings.AI_SERVICE_SECRET = 'http://ai.test', 's' * 40
        settings.AI_SEARCH_ENABLED = False

    def test_transcript_captions_and_chapters(self, alice, fake_ffmpeg, monkeypatch,
                                              django_capture_on_commit_callbacks):
        ai = FakeAI()
        monkeypatch.setattr(ai_client, 'call', ai)
        with django_capture_on_commit_callbacks(execute=True):
            video = process(make_video(alice))
        video.refresh_from_db()
        assert video.status == Video.STATUS_READY and video.captions_status == Video.CAPTIONS_READY
        assert video.transcript.startswith('Welcome') and video.captions_vtt.startswith('WEBVTT')
        assert video.transcript_language == 'en'
        assert video.chapters == [{'start_s': 0.0, 'title': 'Intro'}, {'start_s': 150.0, 'title': 'The fire'}]
        path, payload, user_id = ai.calls[0]
        assert path == '/v1/transcribe' and payload['mimetype'] == 'audio/webm' and payload['purpose'] == 'video'
        assert user_id == alice.id
        assert ai.calls[1][0] == '/v1/video/chapters' and ai.calls[1][1]['utterances'][1]['start'] == 150.0
        assert not default_storage.exists(audio_key(video))  # caption audio is temporary
        argv = next(c for c in fake_ffmpeg.calls if c[-1].endswith('audio.webm'))
        assert argv[argv.index('-ac') + 1] == '1' and argv[argv.index('-ar') + 1] == '16000'

    def test_ai_outage_retries_then_video_stays_ready(self, alice, fake_ffmpeg, monkeypatch):
        ai = FakeAI(error=ai_client.AIUnavailable('down'))
        monkeypatch.setattr(ai_client, 'call', ai)
        video = process(make_video(alice))
        assert video.captions_status == Video.CAPTIONS_PENDING
        assert tasks.caption_video.apply(args=[video.pk], retries=3).get() == 'unavailable'
        video.refresh_from_db()
        assert video.status == Video.STATUS_READY and video.captions_status == Video.CAPTIONS_UNAVAILABLE
        assert video.captions_vtt == '' and not default_storage.exists(audio_key(video))

    def test_service_503_is_retried(self, alice, fake_ffmpeg, monkeypatch):
        monkeypatch.setattr(ai_client, 'call', FakeAI(error=ai_client.AIRejected(503, 'busy')))
        video = process(make_video(alice))
        from celery.exceptions import Retry
        with pytest.raises(Retry):
            tasks.caption_video.apply(args=[video.pk])

    def test_rejections_are_not_retried(self, alice, fake_ffmpeg, monkeypatch):
        ai = FakeAI(error=ai_client.AIRejected(429, 'Daily audio allowance used up'))
        monkeypatch.setattr(ai_client, 'call', ai)
        video = process(make_video(alice))
        assert tasks.caption_video.apply(args=[video.pk]).get() == 'unavailable' and len(ai.calls) == 1

    def test_chapters_failure_keeps_captions(self, alice, fake_ffmpeg, monkeypatch):
        ai = FakeAI()

        def call(path, payload, user_id):
            if path == '/v1/video/chapters':
                raise ai_client.AIUnavailable('down')
            return ai(path, payload, user_id)
        monkeypatch.setattr(ai_client, 'call', call)
        video = process(make_video(alice))
        tasks.caption_video.apply(args=[video.pk])
        video.refresh_from_db()
        assert video.captions_status == Video.CAPTIONS_READY and video.chapters == []

    def test_oversized_audio_is_never_sent(self, alice, fake_ffmpeg, monkeypatch, settings):
        ai = FakeAI()
        monkeypatch.setattr(ai_client, 'call', ai)
        settings.WATCH_MAX_CAPTION_AUDIO_BYTES = 4
        video = process(make_video(alice))
        assert video.captions_status == Video.CAPTIONS_NONE and ai.calls == []

    def test_invalid_vtt_is_dropped(self, alice, fake_ffmpeg, monkeypatch):
        ai = FakeAI()
        ai.transcribe = {**ai.transcribe, 'vtt': '<script>alert(1)</script>'}
        monkeypatch.setattr(ai_client, 'call', ai)
        video = process(make_video(alice))
        tasks.caption_video.apply(args=[video.pk])
        video.refresh_from_db()
        assert video.captions_vtt == '' and video.captions_status == Video.CAPTIONS_UNAVAILABLE

    def test_short_videos_get_no_chapters_call(self, alice, fake_ffmpeg, monkeypatch):
        fake_ffmpeg.probe['format']['duration'] = '45'
        ai = FakeAI()
        monkeypatch.setattr(ai_client, 'call', ai)
        video = process(make_video(alice))
        tasks.caption_video.apply(args=[video.pk])
        assert [c[0] for c in ai.calls] == ['/v1/transcribe']


def test_clean_chapters_rules():
    raw = [{'start_s': 12, 'title': '  Intro <b>here</b> https://evil.example '},
           {'start_s': 15, 'title': 'Too close'},
           {'start_s': 400, 'title': 'Past the end'},
           {'start_s': 100, 'title': ''},
           {'start_s': 'x', 'title': 'Bad'},
           {'start_s': 90, 'title': 'Recipe ' * 30},
           {'start_s': 60, 'title': 'Out of order'}]
    out = captions.clean_chapters(raw, 300)
    assert [c['start_s'] for c in out] == [0.0, 90.0]
    assert out[0]['title'] == 'Intro bhere/b' and len(out[1]['title']) <= captions.MAX_CHAPTER_TITLE
    assert captions.clean_chapters([{'start_s': 0, 'title': 'Only one'}], 300) == []
    many = [{'start_s': i * 20, 'title': f'Part {i}'} for i in range(30)]
    assert len(captions.clean_chapters(many, 1000)) == captions.MAX_CHAPTERS
    assert captions.clean_chapters('nonsense', 100) == []


# ── Subscribers ──────────────────────────────────────────────────────────────

class TestSubscriberNotifications:
    def test_subscribers_notified_once_blocked_users_skipped(self, alice, bob, fake_ffmpeg,
                                                             django_capture_on_commit_callbacks):
        carol, mallory = make_user('carol'), make_user('mallory')
        for u in (bob, carol, mallory):
            ChannelSubscription.objects.create(subscriber=u, channel=alice)
        Block.objects.create(blocker=alice, blocked=mallory)
        with django_capture_on_commit_callbacks(execute=True):
            video = process(make_video(alice))
        notes = Notification.objects.filter(extra__kind='new_video')
        assert sorted(notes.values_list('recipient__username', flat=True)) == ['bob', 'carol']
        n = notes.first()
        assert n.notification_type == Notification.TYPE_SYSTEM and n.extra['video_id'] == video.pk
        assert tasks.notify_subscribers(video.pk) == 0  # never twice
        assert notes.count() == 2

    def test_private_videos_notify_nobody(self, alice, bob, fake_ffmpeg, django_capture_on_commit_callbacks):
        ChannelSubscription.objects.create(subscriber=bob, channel=alice)
        with django_capture_on_commit_callbacks(execute=True):
            process(make_video(alice, is_public=False))
        assert not Notification.objects.filter(extra__kind='new_video').exists()


# ── Visibility moves, deletion ───────────────────────────────────────────────

class TestAssetLifecycle:
    def test_making_private_moves_files_off_the_public_prefix(self, alice, bob, fake_ffmpeg,
                                                             django_capture_on_commit_callbacks):
        video = process(make_video(alice))
        with django_capture_on_commit_callbacks(execute=True):
            r = client_for(alice).patch(reverse('video-detail', kwargs={'pk': video.pk}), {'is_public': False},
                                        format='json')
        assert r.status_code == 200
        video.refresh_from_db()
        assert video.asset_root == 'private'
        for rel in video.asset_files:
            assert default_storage.exists(asset_key(video, rel, 'private'))
            assert not default_storage.exists(asset_key(video, rel, 'public'))
        body = client_for(alice).get(reverse('video-detail', kwargs={'pk': video.pk})).json()
        assert body['playback_url'].startswith('/api/watch/stream/')

    def test_making_public_moves_files_and_notifies(self, alice, bob, fake_ffmpeg,
                                                    django_capture_on_commit_callbacks):
        ChannelSubscription.objects.create(subscriber=bob, channel=alice)
        with django_capture_on_commit_callbacks(execute=True):
            video = process(make_video(alice, is_public=False))
        with django_capture_on_commit_callbacks(execute=True):
            client_for(alice).patch(reverse('video-detail', kwargs={'pk': video.pk}), {'is_public': True},
                                    format='json')
        video.refresh_from_db()
        assert video.asset_root == 'public' and default_storage.exists(asset_key(video, 'master.m3u8'))
        assert Notification.objects.filter(recipient=bob, extra__video_id=video.pk).count() == 1

    def test_visibility_flip_during_processing_is_honoured(self, alice, fake_ffmpeg, monkeypatch,
                                                           django_capture_on_commit_callbacks):
        video = make_video(alice)
        real = tasks._render

        def flip_midway(v, src, out, tmp):
            Video.objects.filter(pk=v.pk).update(is_public=False)
            return real(v, src, out, tmp)
        monkeypatch.setattr(tasks, '_render', flip_midway)
        with django_capture_on_commit_callbacks(execute=True):
            video = process(video)
        video.refresh_from_db()
        assert video.asset_root == 'private' and not default_storage.exists(asset_key(video, 'master.m3u8',
                                                                                         'public'))

    def test_deleting_a_video_erases_its_media(self, alice, fake_ffmpeg, django_capture_on_commit_callbacks):
        video = process(make_video(alice))
        keys = [asset_key(video, rel) for rel in video.asset_files] + [video.video_file.name]
        with django_capture_on_commit_callbacks(execute=True):
            assert client_for(alice).delete(reverse('video-detail', kwargs={'pk': video.pk})).status_code == 204
        assert not any(default_storage.exists(k) for k in keys)


# ── API ──────────────────────────────────────────────────────────────────────

class TestUploadAPI:
    def test_upload_queues_processing_after_commit(self, alice, monkeypatch, django_capture_on_commit_callbacks):
        queued = []
        monkeypatch.setattr(tasks.process_video, 'delay', queued.append)
        with django_capture_on_commit_callbacks(execute=True):
            r = client_for(alice).post(reverse('video-list'), {
                'title': 'Braai', 'video_file': SimpleUploadedFile('c.mp4', MP4, content_type='video/mp4'),
            }, format='multipart')
        assert r.status_code == 201, r.content
        body = r.json()
        assert body['status'] == 'processing' and body['playback_url'] is None
        assert 'video_file' not in body and queued == [body['id']]

    def test_upload_requires_a_file(self, alice):
        r = client_for(alice).post(reverse('video-list'), {'title': 'x'}, format='multipart')
        assert r.status_code == 400

    def test_too_many_uploads_processing_at_once(self, alice, monkeypatch, settings):
        settings.WATCH_MAX_PROCESSING_PER_USER = 1
        make_video(alice)
        r = client_for(alice).post(reverse('video-list'), {
            'title': 'x', 'video_file': SimpleUploadedFile('c.mp4', MP4)}, format='multipart')
        assert r.status_code == 429

    def test_media_cannot_be_replaced_by_edit(self, alice):
        video = make_video(alice, status='ready')
        r = client_for(alice).patch(reverse('video-detail', kwargs={'pk': video.pk}),
                                    {'video_file': SimpleUploadedFile('c.mp4', MP4)}, format='multipart')
        assert r.status_code == 400

    def test_tags_are_validated(self, alice):
        video = make_video(alice, status='ready')
        url = reverse('video-detail', kwargs={'pk': video.pk})
        assert client_for(alice).patch(url, {'tags': ['x' * 50]}, format='json').status_code == 400
        assert client_for(alice).patch(url, {'tags': list('abcdefghijk')}, format='json').status_code == 400
        assert client_for(alice).patch(url, {'tags': [' food ']}, format='json').json()['tags'] == ['food']

    def test_failed_upload_shows_reason_to_owner_and_can_be_retried(self, alice, monkeypatch,
                                                                     django_capture_on_commit_callbacks):
        queued = []
        monkeypatch.setattr(tasks.process_video, 'delay', queued.append)
        video = make_video(alice, status='failed', failure_reason='Videos can be at most 20 minutes long.')
        c = client_for(alice)
        assert c.get(reverse('video-detail', kwargs={'pk': video.pk})).json()['failure_reason'].startswith('Videos')
        with django_capture_on_commit_callbacks(execute=True):
            assert c.post(reverse('video-retry', kwargs={'pk': video.pk})).status_code == 200
        video.refresh_from_db()
        assert video.status == 'processing' and queued == [video.pk]


class TestPlayback:
    def test_public_ready_video_plays_from_public_media(self, alice, bob, fake_ffmpeg):
        video = process(make_video(alice))
        body = client_for(bob).get(reverse('video-detail', kwargs={'pk': video.pk})).json()
        assert body['playback_type'] == 'hls'
        assert body['playback_url'].startswith('/media/public/watch/hls/') and body['playback_url'].endswith(
            'master.m3u8')
        assert body['thumbnail_url'].endswith('thumb.jpg')

    def test_private_video_plays_through_signed_links(self, alice, fake_ffmpeg):
        video = process(make_video(alice, is_public=False))
        c = client_for(alice)
        body = c.get(reverse('video-detail', kwargs={'pk': video.pk})).json()
        assert body['playback_url'].startswith('/api/watch/stream/')
        r = c.get(body['playback_url'])
        assert r.status_code == 200 and r['Content-Type'] == 'application/vnd.apple.mpegurl'
        assert r['Cache-Control'] == 'private, no-store' and r['X-Content-Type-Options'] == 'nosniff'
        # Relative segment URLs inside the playlist resolve under the same link.
        seg = body['playback_url'].rsplit('/', 1)[0] + '/360p/seg_00000.ts'
        r = c.get(seg)
        assert r.status_code == 200 and r['Content-Type'] == 'video/mp2t'

    def test_legacy_public_file_falls_back_to_direct_playback(self, alice, bob):
        video = Video.objects.create(uploader=alice, title='old', video_file='public/watch/videos/x.mp4',
                                     status='ready')
        body = client_for(bob).get(reverse('video-detail', kwargs={'pk': video.pk})).json()
        assert body['playback_type'] == 'file' and body['playback_url'].endswith('x.mp4')

    def test_views_counted_once_per_viewer_never_for_uploader(self, alice, bob):
        video = make_video(alice, status='ready')
        url = reverse('video-detail', kwargs={'pk': video.pk})
        for _ in range(3):
            client_for(bob).get(url)
            client_for(alice).get(url)
        video.refresh_from_db()
        assert video.views_count == 1 and VideoView.objects.filter(video=video).count() == 1

    def test_captions_and_transcript(self, alice, bob):
        video = make_video(alice, status='ready', captions_vtt='WEBVTT\n\n', transcript='Hello', chapters=[
            {'start_s': 0, 'title': 'Intro'}])
        c = client_for(bob)
        r = c.get(reverse('video-captions', kwargs={'pk': video.pk}))
        assert r.status_code == 200 and r['Content-Type'].startswith('text/vtt')
        assert r.content.startswith(b'WEBVTT')
        assert c.get(reverse('video-transcript', kwargs={'pk': video.pk})).json()['transcript'] == 'Hello'
        body = c.get(reverse('video-detail', kwargs={'pk': video.pk})).json()
        assert body['has_captions'] and body['chapters'][0]['title'] == 'Intro'
        bare = make_video(alice, status='ready')
        assert c.get(reverse('video-captions', kwargs={'pk': bare.pk})).status_code == 404


class TestProgressAndHistory:
    def test_progress_saved_clamped_and_resumed(self, alice, bob):
        video = make_video(alice, status='ready', duration=120)
        c = client_for(bob)
        url = reverse('video-progress', kwargs={'pk': video.pk})
        assert c.post(url, {'position_s': 42.26}, format='json').json() == {'position_s': 42.3}
        assert c.post(url, {'position_s': 9000}, format='json').json() == {'position_s': 120.0}
        assert c.post(url, {'position_s': -1}, format='json').status_code == 400
        assert c.post(url, {'position_s': 'soon'}, format='json').status_code == 400
        assert WatchProgress.objects.filter(user=bob, video=video).count() == 1
        assert c.get(url).json() == {'position_s': 120.0}
        assert c.get(reverse('video-detail', kwargs={'pk': video.pk})).json()['resume_position_s'] == 120.0

    def test_history_lists_own_entries_newest_first(self, alice, bob):
        a, b = make_video(alice, status='ready', duration=60), make_video(alice, status='ready', duration=60)
        c = client_for(bob)
        c.post(reverse('video-progress', kwargs={'pk': a.pk}), {'position_s': 5}, format='json')
        c.post(reverse('video-progress', kwargs={'pk': b.pk}), {'position_s': 6}, format='json')
        WatchProgress.objects.create(user=alice, video=a, position_s=1)
        results = c.get(reverse('watch-history-list')).json()['results']
        assert [r['video']['id'] for r in results] == [b.pk, a.pk]
        assert c.delete(reverse('watch-history-detail', kwargs={'video_id': b.pk})).status_code == 204
        assert [r['video']['id'] for r in c.get(reverse('watch-history-list')).json()['results']] == [a.pk]
        assert c.delete(reverse('watch-history-clear')).status_code == 204
        assert not WatchProgress.objects.filter(user=bob).exists()
        assert WatchProgress.objects.filter(user=alice).exists()


class TestChannels:
    def test_subscribe_unsubscribe_and_feed(self, alice, bob):
        mine = make_video(alice, status='ready')
        make_video(make_user('carol'), status='ready')
        c = client_for(bob)
        r = c.post(reverse('channel-subscribe', kwargs={'pk': alice.pk}))
        assert r.status_code == 201 and r.json()['is_subscribed'] and r.json()['subscribers_count'] == 1
        assert c.post(reverse('channel-subscribe', kwargs={'pk': alice.pk})).json()['subscribers_count'] == 1
        feed = c.get(reverse('video-list'), {'feed': 'subscriptions'}).json()['results']
        assert [v['id'] for v in feed] == [mine.pk]
        assert [s['user']['id'] for s in c.get(reverse('channel-list')).json()['results']] == [alice.pk]
        summary = c.get(reverse('channel-detail', kwargs={'pk': alice.pk})).json()
        assert summary['videos_count'] == 1 and summary['user']['username'] == 'alice'
        assert c.delete(reverse('channel-subscribe', kwargs={'pk': alice.pk})).json()['is_subscribed'] is False

    def test_cannot_subscribe_to_self(self, alice):
        assert client_for(alice).post(reverse('channel-subscribe', kwargs={'pk': alice.pk})).status_code == 400

    def test_videos_tab_filters_by_uploader(self, alice, bob):
        mine = make_video(alice, status='ready')
        make_video(bob, status='ready')
        res = client_for(bob).get(reverse('video-list'), {'uploader': alice.pk}).json()['results']
        assert [v['id'] for v in res] == [mine.pk]
        assert client_for(bob).get(reverse('video-list'), {'uploader': 'x'}).status_code == 400


def test_stream_token_round_trip():
    from .access import read_stream_token
    assert read_stream_token(stream_token(5, 7)) == (5, 7)
    assert read_stream_token(stream_token(5, 7)[:-2] + 'xx') is None
    assert read_stream_token('garbage') is None
