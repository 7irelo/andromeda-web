"""
Generate variants when an avatar or post image is uploaded, and delete them
with the row (``core.media_cleanup`` takes the original).

Generation runs in-process right after the save: the upload is still in
memory, it takes a fraction of a second, and the uploader's next response
already has working ``srcset`` URLs. A failure is logged and never fails the
upload; ``manage.py generate_image_variants`` backfills.
"""
import logging

from django.db import transaction
from django.db.models.signals import post_delete, post_init, post_save

from . import variants

logger = logging.getLogger(__name__)


def _fields():
    from posts.models import Post, PostMedia
    from users.models import User

    return {
        User: [('avatar', variants.AVATAR_WIDTHS)],
        Post: [('image', variants.POST_WIDTHS)],
        PostMedia: [('file', variants.POST_WIDTHS)],
    }


def _attr(field):
    return f'_imaging_{field}'


def _make_handlers(fields):
    def remember(sender, instance, **kwargs):
        for field, _ in fields:
            if field in instance.__dict__:
                f = instance.__dict__[field]
                setattr(instance, _attr(field), getattr(f, 'name', f) or '')

    def saved(sender, instance, update_fields=None, **kwargs):
        for field, widths in fields:
            if update_fields is not None and field not in update_fields:
                continue
            f = getattr(instance, field)
            name = f.name if f else ''
            if name and name != getattr(instance, _attr(field), None):
                if getattr(instance, 'media_type', 'image') != 'image':
                    continue
                try:
                    variants.generate(f, widths)
                except Exception:
                    logger.warning('Image variants failed for %s', name, exc_info=True)
            setattr(instance, _attr(field), name)

    def deleted(sender, instance, **kwargs):
        for field, widths in fields:
            f = getattr(instance, field)
            if f and f.name:
                storage, name = f.storage, f.name
                transaction.on_commit(lambda s=storage, n=name, w=widths: variants.delete(s, n, w))

    return remember, saved, deleted


def connect():
    for model, fields in _fields().items():
        remember, saved, deleted = _make_handlers(fields)
        label = model._meta.label
        post_init.connect(remember, sender=model, weak=False, dispatch_uid=f'imaging-init-{label}')
        post_save.connect(saved, sender=model, weak=False, dispatch_uid=f'imaging-save-{label}')
        post_delete.connect(deleted, sender=model, weak=False, dispatch_uid=f'imaging-delete-{label}')
