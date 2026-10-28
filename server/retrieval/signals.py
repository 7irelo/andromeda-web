from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from marketplace.models import Listing
from groups.models import Group
from pages.models import Page
from posts.models import Comment, Post
from watch.models import Video

from .tasks import queue_index, remove_object

_KIND = {Post: 'posts', Listing: 'listings', Group: 'groups', Page: 'pages', Video: 'videos'}


def _saved(sender, instance, **kwargs):
    queue_index(_KIND[sender], instance.pk)


def _deleted(sender, instance, **kwargs):
    # Deletion is erasure: drop the vectors synchronously with the row.
    remove_object.run(_KIND[sender], instance.pk)


for model in _KIND:
    post_save.connect(_saved, sender=model, dispatch_uid=f'retrieval-save-{model.__name__}')
    post_delete.connect(_deleted, sender=model, dispatch_uid=f'retrieval-delete-{model.__name__}')


@receiver([post_save, post_delete], sender=Comment, dispatch_uid='retrieval-comment')
def _comment_changed(sender, instance, **kwargs):
    # Top comments are part of the post's document.
    queue_index('posts', instance.post_id)
