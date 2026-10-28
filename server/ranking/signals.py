"""Engagement with a post the viewer was shown in their feed turns its impression positive."""
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from posts.models import Comment, Like, Post, SavedPost

from .impressions import mark_engaged


def _later(user_id, post_id):
    transaction.on_commit(lambda: mark_engaged(user_id, post_id))


@receiver(post_save, sender=Like, dispatch_uid='ranking-like')
def _liked(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        _later(instance.user_id, instance.post_id)


@receiver(post_save, sender=Comment, dispatch_uid='ranking-comment')
def _commented(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        _later(instance.author_id, instance.post_id)


@receiver(post_save, sender=SavedPost, dispatch_uid='ranking-save')
def _saved(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        _later(instance.user_id, instance.post_id)


@receiver(post_save, sender=Post, dispatch_uid='ranking-share')
def _shared(sender, instance, created, raw=False, **kwargs):
    if created and not raw and instance.shared_post_id:
        _later(instance.author_id, instance.shared_post_id)
