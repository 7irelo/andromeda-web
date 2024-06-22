"""
Keep Neo4j UserNode in sync with the PostgreSQL User model.
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import User, FriendRequest


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


@receiver(post_delete, sender=User)
def remove_user_from_neo4j(sender, instance, **kwargs):
    try:
        from users.graph_models import UserNode
        node = UserNode.nodes.get_or_none(user_id=instance.id)
        if node:
            node.delete()
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
