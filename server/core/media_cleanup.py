"""
Delete stored files when the rows that own them are deleted.

Django leaves files behind on delete. For a social network that's a privacy
bug: account erasure, post deletion and moderation removals must take the
photos, videos and voice notes with them. Files are deleted after the
transaction commits, so a rolled-back delete never loses data.
"""
import logging

from django.apps import apps
from django.db import models, transaction
from django.db.models.signals import post_delete

logger = logging.getLogger(__name__)


def _delete_files(sender, instance, **kwargs):
    for field in sender._meta.concrete_fields:
        if not isinstance(field, models.FileField):
            continue
        f = getattr(instance, field.name)
        if not f or not f.name:
            continue
        storage, name = f.storage, f.name

        def remove(storage=storage, name=name):
            try:
                storage.delete(name)
            except Exception:
                logger.warning('Could not delete %s', name, exc_info=True)
        transaction.on_commit(remove)


def connect():
    for model in apps.get_models():
        if any(isinstance(f, models.FileField) for f in model._meta.concrete_fields):
            post_delete.connect(_delete_files, sender=model, dispatch_uid=f'media-cleanup-{model._meta.label}')
