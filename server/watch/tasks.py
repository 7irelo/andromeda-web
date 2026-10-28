"""
The video pipeline.

process_video (``video`` queue, its own single-slot worker) probes the upload,
renders a thumbnail and sprite strip, transcodes 360p/720p HLS and extracts a
small audio track for captions. Each step is queued after commit and is safe
to repeat: a run claims the video first, writes to a fixed asset folder, and
overwrites whatever a failed attempt left behind. Then:

- caption_video sends the audio to the AI service for a transcript, WebVTT
  captions and chapters. Without the AI service the video is simply ready
  without captions.
- notify_subscribers tells the uploader's subscribers, once per video, and
  only about public videos.
- relocate_assets moves processed files between the public and private
  prefixes when the uploader changes who can see the video.
"""
import base64
import logging
import shutil
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from PIL import Image

from core import ai_client, visibility
from . import captions, ffmpeg
from .access import ASSET_PATH_RE, CONTENT_TYPES, asset_dir, asset_key, audio_key
from .models import ChannelSubscription, Video

logger = logging.getLogger(__name__)

STALE_CLAIM = timedelta(hours=2)
GENERIC_FAILURE = 'Processing failed. Please try uploading again.'


def queue_processing(video_id):
    transaction.on_commit(lambda: process_video.delay(video_id))


# ── Storage helpers ──────────────────────────────────────────────────────────

def _put(key, path):
    """Write ``path`` to storage at exactly ``key`` (retries overwrite)."""
    if default_storage.exists(key):
        default_storage.delete(key)
    with open(path, 'rb') as fh:
        f = File(fh, name=key)
        f.content_type = CONTENT_TYPES.get(Path(key).suffix, 'application/octet-stream')
        saved = default_storage.save(key, f)
    if saved != key:
        raise OSError(f'storage renamed {key} to {saved}')


def _copy(src_key, dest_key):
    if default_storage.exists(dest_key):
        default_storage.delete(dest_key)
    with default_storage.open(src_key, 'rb') as fh:
        f = File(fh, name=dest_key)
        f.content_type = CONTENT_TYPES.get(Path(dest_key).suffix, 'application/octet-stream')
        saved = default_storage.save(dest_key, f)
    if saved != dest_key:
        raise OSError(f'storage renamed {dest_key} to {saved}')


def _delete_keys(keys):
    for key in keys:
        try:
            default_storage.delete(key)
        except Exception:  # best effort: an orphaned file is not worth failing over
            logger.warning('Could not delete %s', key, exc_info=True)


def _delete_tree(prefix):
    try:
        dirs, files = default_storage.listdir(prefix)
    except (FileNotFoundError, NotADirectoryError):
        return
    except Exception:
        logger.warning('Could not list %s', prefix, exc_info=True)
        return
    _delete_keys(f'{prefix}/{f}' for f in files)
    for d in dirs:
        _delete_tree(f'{prefix}/{d}')


# ── Processing ───────────────────────────────────────────────────────────────

def _download(field, dest):
    with field.open('rb') as src, open(dest, 'wb') as out:
        shutil.copyfileobj(src, out, 1024 * 1024)


def _custom_thumbnail(field, dest):
    with field.open('rb') as fh:
        img = Image.open(fh)
        img.load()
    img = img.convert('RGB')
    img.thumbnail((1280, 1280))
    img.save(dest, format='JPEG', quality=85)


def _render(video, src, out, tmp):
    """Run ffmpeg into ``out``. Returns (probe, renditions, audio path or None)."""
    p = ffmpeg.probe(src)
    limit = settings.WATCH_MAX_DURATION_SECONDS
    if p.duration > limit:
        raise ffmpeg.ProcessingError(f'Videos can be at most {limit // 60} minutes long.')

    if video.thumbnail:
        try:
            _custom_thumbnail(video.thumbnail, out / 'thumb.jpg')
        except (OSError, ValueError, Image.DecompressionBombError):
            ffmpeg.thumbnail(src, out / 'thumb.jpg', p)
    else:
        ffmpeg.thumbnail(src, out / 'thumb.jpg', p)
    try:
        ffmpeg.sprite(src, out / 'sprite.jpg', p)
    except ffmpeg.ProcessingError as exc:
        logger.info('Sprite skipped for video %s: %s', video.pk, exc)
        (out / 'sprite.jpg').unlink(missing_ok=True)

    variants = []
    for target in ffmpeg.renditions_for(p):
        name = f'{target}p'
        width, height = ffmpeg.hls(src, out / name, p, target)
        size = sum(f.stat().st_size for f in (out / name).iterdir())
        variants.append((name, width, height, max(size * 8 / p.duration, 64_000) * 1.1))
    (out / 'master.m3u8').write_text(ffmpeg.master_playlist(variants), encoding='utf-8')

    audio = None
    if p.has_audio and ai_client.enabled():
        try:
            ffmpeg.extract_audio(src, tmp / 'audio.webm')
            audio = tmp / 'audio.webm'
            if audio.stat().st_size > settings.WATCH_MAX_CAPTION_AUDIO_BYTES or audio.stat().st_size == 0:
                logger.info('Audio for video %s too large for captions', video.pk)
                audio = None
        except ffmpeg.ProcessingError as exc:
            logger.info('No caption audio for video %s: %s', video.pk, exc)
            audio = None
    return p, [int(v[0][:-1]) for v in variants], audio


def _fail(video_id, reason):
    video = Video.objects.filter(pk=video_id).first()
    if video is None:
        return
    Video.objects.filter(pk=video_id).update(status=Video.STATUS_FAILED, failure_reason=reason[:255],
                                             processing_started_at=None)
    if video.asset_id:
        for root in ('public', 'private'):
            _delete_tree(asset_dir(video, root))
        _delete_keys([audio_key(video)])


@shared_task(name='watch.tasks.process_video', bind=True, queue='video', max_retries=3,
             soft_time_limit=85 * 60, time_limit=90 * 60)
def process_video(self, video_id):
    now = timezone.now()
    claimed = Video.objects.filter(pk=video_id, status=Video.STATUS_PROCESSING).filter(
        Q(processing_started_at__isnull=True) | Q(processing_started_at__lt=now - STALE_CLAIM)
    ).update(processing_started_at=now)
    if not claimed:
        return 'skipped'
    video = Video.objects.get(pk=video_id)
    if not video.asset_id:
        # Fixed before any work so a retry writes over the same folder.
        video.asset_id = uuid.uuid4().hex
        Video.objects.filter(pk=video_id).update(asset_id=video.asset_id)
    asset_id = video.asset_id
    root = 'public' if video.is_public else 'private'

    try:
        with tempfile.TemporaryDirectory(prefix='andromeda-video-') as tmp:
            tmp = Path(tmp)
            out = tmp / 'out'
            out.mkdir()
            src = tmp / 'source'
            _download(video.video_file, src)
            p, renditions, audio = _render(video, src, out, tmp)
            files = sorted(f.relative_to(out).as_posix() for f in out.rglob('*') if f.is_file())
            if not all(ASSET_PATH_RE.match(f) for f in files):
                raise ffmpeg.ProcessingError(GENERIC_FAILURE, f'unexpected output files: {files}')
            for rel in files:
                _put(asset_key(video, rel, root), out / rel)
            if audio:
                _put(audio_key(video), audio)
    except ffmpeg.ProcessingError as exc:
        logger.warning('Video %s failed: %s', video_id, exc)
        _fail(video_id, exc.reason)
        return 'failed'
    except SoftTimeLimitExceeded:
        _fail(video_id, 'Processing this video took too long.')
        return 'failed'
    except Exception as exc:
        # Storage hiccups, a missing ffmpeg binary, a worker running out of disk...
        logger.exception('Video %s processing error (attempt %s)', video_id, self.request.retries + 1)
        if self.request.retries >= self.max_retries:
            _fail(video_id, GENERIC_FAILURE)
            return 'failed'
        Video.objects.filter(pk=video_id).update(processing_started_at=None)
        raise self.retry(exc=exc, countdown=60 * 2 ** self.request.retries) from None

    with transaction.atomic():
        video = Video.objects.select_for_update().filter(pk=video_id).first()
        if video is None:  # deleted while processing: nothing will reference these files
            for r in ('public', 'private'):
                _delete_tree(f'{r}/watch/hls/{asset_id}')
            _delete_keys([f'private/watch/audio/{asset_id}.webm'])
            return 'deleted'
        video.status = Video.STATUS_READY
        video.failure_reason = ''
        video.processing_started_at = None
        video.duration = int(round(p.duration))
        video.width, video.height = p.width, p.height
        video.asset_root = root
        video.asset_files = files
        video.renditions = renditions
        video.captions_status = Video.CAPTIONS_PENDING if audio else Video.CAPTIONS_NONE
        video.save()
        moved = video.is_public != (root == 'public')
        transaction.on_commit(lambda: _after_ready(video_id, bool(audio), moved))
    return 'ready'


def _after_ready(video_id, has_audio, moved):
    if has_audio:
        caption_video.delay(video_id)
    if moved:
        relocate_assets.delay(video_id)  # notifies once the files are public
    else:
        notify_subscribers.delay(video_id)


@shared_task(name='watch.tasks.requeue_stuck_videos', queue='default')
def requeue_stuck_videos():
    """Beat safety net: re-queue uploads whose worker died mid-run or whose message was lost."""
    cutoff = timezone.now() - STALE_CLAIM
    stuck = list(Video.objects.filter(status=Video.STATUS_PROCESSING).filter(
        Q(processing_started_at__lt=cutoff) | Q(processing_started_at__isnull=True, created_at__lt=cutoff)
    ).values_list('pk', flat=True)[:50])
    for pk in stuck:
        process_video.delay(pk)
    return len(stuck)


# ── Captions & chapters ──────────────────────────────────────────────────────

def _captions_done(video, status):
    Video.objects.filter(pk=video.pk).update(captions_status=status)
    _delete_keys([audio_key(video)])


def _chapters(video, utterances):
    if video.duration < captions.MIN_DURATION_FOR_CHAPTERS_S or not utterances:
        return []
    payload = {'title': video.title[:255], 'duration_s': float(video.duration), 'utterances': utterances}
    try:
        res = ai_client.call('/v1/video/chapters', payload, user_id=video.uploader_id)
    except (ai_client.AIUnavailable, ai_client.AIRejected) as exc:
        logger.info('No chapters for video %s: %s', video.pk, exc)
        return []
    return captions.clean_chapters(res.get('chapters'), video.duration)


@shared_task(name='watch.tasks.caption_video', bind=True, queue='default', max_retries=3)
def caption_video(self, video_id):
    video = Video.objects.filter(pk=video_id, status=Video.STATUS_READY).first()
    if video is None or video.captions_status != Video.CAPTIONS_PENDING:
        return 'skipped'
    if not ai_client.enabled():
        _captions_done(video, Video.CAPTIONS_UNAVAILABLE)
        return 'unavailable'
    key = audio_key(video)
    try:
        with default_storage.open(key, 'rb') as fh:
            audio = fh.read(settings.WATCH_MAX_CAPTION_AUDIO_BYTES + 1)
    except FileNotFoundError:
        audio = b''
    if not audio or len(audio) > settings.WATCH_MAX_CAPTION_AUDIO_BYTES:
        _captions_done(video, Video.CAPTIONS_UNAVAILABLE)
        return 'unavailable'

    try:
        res = ai_client.call('/v1/transcribe', {'audio_b64': base64.b64encode(audio).decode(),
                                                'mimetype': 'audio/webm', 'purpose': 'video'},
                             user_id=video.uploader_id)
    except (ai_client.AIUnavailable, ai_client.AIRejected) as exc:
        if captions.is_transient(exc) and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=120 * 2 ** self.request.retries) from None
        logger.info('Captions unavailable for video %s: %s', video_id, exc)
        _captions_done(video, Video.CAPTIONS_UNAVAILABLE)
        return 'unavailable'

    vtt = captions.clean_vtt(res.get('vtt'))
    video.transcript = captions.clean_transcript(res.get('transcript'))
    video.transcript_language = str(res.get('language') or '')[:16]
    video.captions_vtt = vtt
    video.chapters = _chapters(video, captions.utterances_payload(res.get('utterances')))
    video.captions_status = Video.CAPTIONS_READY if vtt else Video.CAPTIONS_UNAVAILABLE
    # save() rather than update(): post_save re-indexes the transcript for semantic search.
    video.save(update_fields=['transcript', 'transcript_language', 'captions_vtt', 'chapters',
                              'captions_status', 'updated_at'])
    _delete_keys([key])
    return 'ready' if vtt else 'no-speech'


# ── Subscribers ──────────────────────────────────────────────────────────────

@shared_task(name='watch.tasks.notify_subscribers', queue='notifications')
def notify_subscribers(video_id):
    from notifications.models import Notification
    from notifications.tasks import _push_to_websocket

    with transaction.atomic():
        # The timestamp doubles as the "already notified" flag, claimed atomically.
        claimed = Video.objects.filter(pk=video_id, status=Video.STATUS_READY, is_public=True,
                                       subscribers_notified_at__isnull=True).update(
            subscribers_notified_at=timezone.now())
        if not claimed:
            return 0
        video = Video.objects.select_related('uploader').get(pk=video_id)
        uploader = video.uploader
        recipients = ChannelSubscription.objects.filter(
            channel_id=uploader.pk, subscriber__is_active=True,
        ).exclude(subscriber_id__in=visibility.blocked_ids(uploader)).values_list('subscriber_id', flat=True)
        title = f'{uploader.username} posted a new video'
        extra = {'kind': 'new_video', 'video_id': video.pk}
        created = Notification.objects.bulk_create([
            Notification(recipient_id=uid, sender=uploader, notification_type=Notification.TYPE_SYSTEM,
                         title=title, body=video.title[:200], extra=extra)
            for uid in recipients
        ], batch_size=500)

    for n in created:
        _push_to_websocket(n.recipient_id, {
            'id': n.id, 'type': Notification.TYPE_SYSTEM, 'title': title, 'sender': uploader.username,
            'video_id': video.pk, 'created_at': n.created_at.isoformat() if n.created_at else None,
        })
    return len(created)


# ── Visibility changes & deletion ────────────────────────────────────────────

@shared_task(name='watch.tasks.relocate_assets', bind=True, queue='default', max_retries=5)
def relocate_assets(self, video_id):
    """Move processed files to the prefix that matches the video's current visibility."""
    video = Video.objects.filter(pk=video_id, status=Video.STATUS_READY).first()
    if video is None or not video.asset_files:
        return 'skipped'
    target = 'public' if video.is_public else 'private'
    source = video.asset_root
    if source == target:
        return 'unchanged'
    try:
        for rel in video.asset_files:
            _copy(asset_key(video, rel, source), asset_key(video, rel, target))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30 * 2 ** self.request.retries) from None
    Video.objects.filter(pk=video_id, asset_root=source).update(asset_root=target)
    _delete_keys(asset_key(video, rel, source) for rel in video.asset_files)
    if Video.objects.filter(pk=video_id).exclude(is_public=(target == 'public')).exists():
        relocate_assets.delay(video_id)  # flipped back while we were copying
    elif target == 'public':
        notify_subscribers.delay(video_id)
    return target


@shared_task(name='watch.tasks.delete_assets', queue='default')
def delete_assets(keys):
    _delete_keys(k for k in keys if isinstance(k, str) and k.startswith(('public/watch/', 'private/watch/')))
