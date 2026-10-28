"""
Bring videos uploaded before the HLS pipeline onto it.

Those videos have no processed assets and play their original file straight
from ``public/``. This queues each one for processing (renditions, thumbnail,
sprite, captions) and moves the original out of ``public/`` whenever the video
isn't public, since a private video's original must not be anonymously
readable. Public videos keep their original in place until processing has
finished, so they stay playable meanwhile; run again with ``--move-public``
afterwards to take those originals private too (playback is HLS by then).
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from watch.models import Video
from watch.tasks import _copy, _delete_keys, queue_processing

LEGACY_PREFIX = 'private/watch/originals/legacy/'


def _private_key(name):
    return LEGACY_PREFIX + name[len('public/'):]


class Command(BaseCommand):
    help = 'Reprocess videos uploaded before the HLS pipeline and move non-public originals out of public/.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='List what would change without changing it.')
        parser.add_argument('--limit', type=int, default=None, help='Process at most this many videos.')
        parser.add_argument('--move-public', action='store_true',
                            help='Also move originals of public, already-processed videos out of public/.')

    def _move_original(self, video, dry_run):
        old = video.video_file.name
        new = _private_key(old)
        self.stdout.write(f'  move {old} -> {new}')
        if dry_run:
            return
        _copy(old, new)
        Video.objects.filter(pk=video.pk).update(video_file=new)
        transaction.on_commit(lambda: _delete_keys([old]))

    def handle(self, *args, dry_run=False, limit=None, move_public=False, **options):
        in_public = Video.objects.filter(video_file__startswith='public/')
        legacy = Video.objects.filter(asset_id='').exclude(status=Video.STATUS_PROCESSING).order_by('pk')
        if limit:
            legacy = legacy[:limit]
        queued = moved = 0
        for video in legacy:
            self.stdout.write(f'video {video.pk}: reprocess')
            with transaction.atomic():
                if video.video_file.name.startswith('public/') and not video.is_public:
                    self._move_original(video, dry_run)
                    moved += 1
                if not dry_run:
                    Video.objects.filter(pk=video.pk).update(status=Video.STATUS_PROCESSING, failure_reason='',
                                                             processing_started_at=None)
                    queue_processing(video.pk)
            queued += 1

        # Originals of non-public videos that were processed already but still sit in public/.
        stragglers = in_public.exclude(asset_id='')
        if not move_public:
            stragglers = stragglers.filter(is_public=False)
        for video in stragglers.order_by('pk'):
            self.stdout.write(f'video {video.pk}: original out of public/')
            with transaction.atomic():
                self._move_original(video, dry_run)
            moved += 1

        prefix = 'Would queue' if dry_run else 'Queued'
        self.stdout.write(self.style.SUCCESS(f'{prefix} {queued} video(s); moved {moved} original(s).'))
