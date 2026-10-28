"""
Who may watch what, and where the bytes come from.

A video is visible to its uploader, and to everyone else once it's ready and
public; blocks hide it in both directions. Every read path (lists, detail,
captions, transcript, streams, history) goes through ``visible_videos``.

Processed assets for public videos sit under the ``public/`` prefix and are
served by nginx straight from object storage. Everything else is streamed by
Django through a signed playback link that names one video and one viewer,
expires, and is re-authorised on every request, so revoking access (making a
video private, blocking someone) takes effect immediately. The link lives in
the path rather than a header so the native player, ``<img>`` and relative
segment URLs inside the playlists all carry it.
"""
import re

from django.conf import settings
from django.core import signing
from django.core.files.storage import default_storage
from django.db.models import Q
from django.urls import reverse

from core import visibility

STREAM_SALT = 'watch.stream'
# The only files a stream link can reach, relative to the video's asset folder.
ASSET_PATH_RE = re.compile(r'^(master\.m3u8|thumb\.jpg|sprite\.jpg|(360|720)p/(index\.m3u8|seg_\d{5}\.ts))$')
CONTENT_TYPES = {'.m3u8': 'application/vnd.apple.mpegurl', '.ts': 'video/mp2t', '.jpg': 'image/jpeg'}


def visible_videos(user, qs=None):
    from .models import Video

    qs = Video.objects.all() if qs is None else qs
    if not user.is_authenticated:
        return qs.none()
    return qs.filter(Q(status=Video.STATUS_READY, is_public=True) | Q(uploader=user)).exclude(
        uploader_id__in=visibility.blocked_ids(user))


def asset_dir(video, root=None):
    return f'{root or video.asset_root}/watch/hls/{video.asset_id}'


def asset_key(video, rel, root=None):
    return f'{asset_dir(video, root)}/{rel}'


def audio_key(video):
    return f'private/watch/audio/{video.asset_id}.webm'


def stream_token(video_id, user_id):
    return signing.dumps([video_id, user_id], salt=STREAM_SALT, compress=False)


def read_stream_token(token):
    """(video_id, user_id) for a valid, unexpired link, else None."""
    try:
        video_id, user_id = signing.loads(token, salt=STREAM_SALT, max_age=settings.WATCH_STREAM_TOKEN_MAX_AGE)
    except (signing.BadSignature, ValueError, TypeError):
        return None
    if not isinstance(video_id, int) or not isinstance(user_id, int):
        return None
    return video_id, user_id


def asset_url(video, rel, user):
    """URL for one processed file, or None if the video has no such file."""
    if rel not in (video.asset_files or []):
        return None
    if video.is_public and video.asset_root == 'public':
        return default_storage.url(asset_key(video, rel))
    if not user or not user.is_authenticated:
        return None
    return reverse('watch-stream', kwargs={'token': stream_token(video.pk, user.pk), 'path': rel})
