from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .access import asset_key, audio_key
from .models import Video


@receiver(post_delete, sender=Video, dispatch_uid='watch-video-deleted')
def _delete_media(sender, instance, **kwargs):
    """Deleting a video erases its media: original, renditions, images and caption audio."""
    from .tasks import delete_assets

    keys = [f.name for f in (instance.video_file, instance.thumbnail) if f]
    if instance.asset_id:
        # Both prefixes, in case a visibility move was in flight.
        keys += [asset_key(instance, rel, root) for rel in instance.asset_files or []
                 for root in ('public', 'private')]
        keys.append(audio_key(instance))
    if keys:
        transaction.on_commit(lambda: delete_assets.delay(keys))
