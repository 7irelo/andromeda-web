"""
Keep Neo4j UserNode in sync with the PostgreSQL User model.
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import User, Follow, FriendRequest


@receiver(post_save, sender=User)
def sync_user_to_neo4j(sender, instance, created, **kwargs):
    try:
        from users.graph_models import UserNode
        node = UserNode.nodes.get_or_none(user_id=instance.id)
        if node is None:
            UserNode(
                user_id=instance.id,
                username=instance.username,
                display_name=instance.full_name,
                is_verified=instance.is_verified,
            ).save()
        else:
            node.username = instance.username
            node.display_name = instance.full_name
            node.is_verified = instance.is_verified
            node.save()
    except Exception:
        pass  # Neo4j unavailable during migrations – non-blocking


@receiver(post_save, sender=Follow)
def create_follow_in_neo4j(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        from users.graph_models import UserNode
        from_node = UserNode.nodes.get_or_none(user_id=instance.follower_id)
        to_node = UserNode.nodes.get_or_none(user_id=instance.following_id)
        if from_node and to_node:
            if not from_node.follows.is_connected(to_node):
                from_node.follows.connect(to_node)
        # Update counters
        User.objects.filter(pk=instance.follower_id).update(
            following_count=User.objects.get(pk=instance.follower_id).following_set.count()
        )
        User.objects.filter(pk=instance.following_id).update(
            followers_count=User.objects.get(pk=instance.following_id).followers_set.count()
        )
    except Exception:
        pass


@receiver(post_delete, sender=Follow)
def remove_follow_from_neo4j(sender, instance, **kwargs):
    try:
        from users.graph_models import UserNode
        from_node = UserNode.nodes.get_or_none(user_id=instance.follower_id)
        to_node = UserNode.nodes.get_or_none(user_id=instance.following_id)
        if from_node and to_node and from_node.follows.is_connected(to_node):
            from_node.follows.disconnect(to_node)
    except Exception:
        pass


@receiver(post_save, sender=FriendRequest)
def handle_friend_request_accepted(sender, instance, **kwargs):
    if instance.status != FriendRequest.STATUS_ACCEPTED:
        return
    try:
        from users.graph_models import UserNode
        node_a = UserNode.nodes.get_or_none(user_id=instance.sender_id)
        node_b = UserNode.nodes.get_or_none(user_id=instance.receiver_id)
        if node_a and node_b and not node_a.friends.is_connected(node_b):
            node_a.friends.connect(node_b)
        # Update counters
        for uid in [instance.sender_id, instance.receiver_id]:
            user = User.objects.get(pk=uid)
            user.friends_count = user.sent_requests.filter(
                status=FriendRequest.STATUS_ACCEPTED
            ).count() + user.received_requests.filter(
                status=FriendRequest.STATUS_ACCEPTED
            ).count()
            user.save(update_fields=['friends_count'])
    except Exception:
        pass
