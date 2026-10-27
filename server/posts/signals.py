from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from users import graph_sync
from .models import Comment, Like, Post


def _recount_posts(author_id):
    from django.contrib.auth import get_user_model
    get_user_model().objects.filter(pk=author_id).update(
        posts_count=Post.objects.filter(author_id=author_id).count()
    )


@receiver(post_save, sender=Post)
def on_post_created(sender, instance, created, **kwargs):
    if created:
        _recount_posts(instance.author_id)
        graph_sync.enqueue(graph_sync.sync_post, instance.id, instance.author_id)


@receiver(post_delete, sender=Post)
def on_post_deleted(sender, instance, **kwargs):
    _recount_posts(instance.author_id)
    graph_sync.enqueue(graph_sync.delete_post, instance.id)


@receiver(post_save, sender=Like)
def on_like_created(sender, instance, created, **kwargs):
    if created:
        Post.objects.filter(pk=instance.post_id).update(
            likes_count=Like.objects.filter(post_id=instance.post_id).count()
        )
        graph_sync.enqueue(graph_sync.link_like, instance.user_id, instance.post_id)


@receiver(post_delete, sender=Like)
def on_like_deleted(sender, instance, **kwargs):
    Post.objects.filter(pk=instance.post_id).update(
        likes_count=Like.objects.filter(post_id=instance.post_id).count()
    )
    graph_sync.enqueue(graph_sync.unlink_like, instance.user_id, instance.post_id)


@receiver(post_save, sender=Comment)
def on_comment_created(sender, instance, created, **kwargs):
    if created:
        Post.objects.filter(pk=instance.post_id).update(
            comments_count=Comment.objects.filter(post_id=instance.post_id).count()
        )


@receiver(post_delete, sender=Comment)
def on_comment_deleted(sender, instance, **kwargs):
    Post.objects.filter(pk=instance.post_id).update(
        comments_count=Comment.objects.filter(post_id=instance.post_id).count()
    )
