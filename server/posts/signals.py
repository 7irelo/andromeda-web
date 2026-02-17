from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Post, Like, Comment


@receiver(post_save, sender=Post)
def sync_post_to_neo4j(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        from users.graph_models import UserNode, PostNode
        post_node = PostNode(post_id=instance.id, author_id=instance.author_id).save()
        author_node = UserNode.nodes.get_or_none(user_id=instance.author_id)
        if author_node and post_node:
            author_node.created_posts.connect(post_node)
        # Update post count
        instance.author.__class__.objects.filter(pk=instance.author_id).update(
            posts_count=Post.objects.filter(author_id=instance.author_id).count()
        )
    except Exception:
        pass


@receiver(post_save, sender=Like)
def on_like_created(sender, instance, created, **kwargs):
    if created:
        Post.objects.filter(pk=instance.post_id).update(
            likes_count=Like.objects.filter(post_id=instance.post_id).count()
        )
        try:
            from users.graph_models import UserNode, PostNode
            user_node = UserNode.nodes.get_or_none(user_id=instance.user_id)
            post_node = PostNode.nodes.get_or_none(post_id=instance.post_id)
            if user_node and post_node and not user_node.liked_posts.is_connected(post_node):
                user_node.liked_posts.connect(post_node)
        except Exception:
            pass


@receiver(post_delete, sender=Like)
def on_like_deleted(sender, instance, **kwargs):
    Post.objects.filter(pk=instance.post_id).update(
        likes_count=Like.objects.filter(post_id=instance.post_id).count()
    )


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
