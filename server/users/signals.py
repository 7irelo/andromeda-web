"""
Keep denormalised counters and the Neo4j projection in sync with Postgres.
"""
from django.db.models import Q
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from . import graph_sync
from .models import FriendRequest, User


def recount_friends(*user_ids):
    for uid in user_ids:
        count = FriendRequest.objects.filter(
            Q(sender_id=uid) | Q(receiver_id=uid), status=FriendRequest.STATUS_ACCEPTED
        ).count()
        User.objects.filter(pk=uid).update(friends_count=count)


@receiver(post_save, sender=User)
def sync_user_to_graph(sender, instance, update_fields=None, **kwargs):
    relevant = {'username', 'first_name', 'last_name', 'is_verified'}
    if update_fields is not None and not relevant & set(update_fields):
        return
    graph_sync.user_changed(instance)


@receiver(post_delete, sender=User)
def remove_user_from_graph(sender, instance, **kwargs):
    graph_sync.user_deleted(instance.id)


@receiver(post_save, sender=FriendRequest)
def on_friend_request_saved(sender, instance, **kwargs):
    if instance.status == FriendRequest.STATUS_ACCEPTED:
        recount_friends(instance.sender_id, instance.receiver_id)
        graph_sync.friends_linked(instance.sender_id, instance.receiver_id)


@receiver(post_delete, sender=FriendRequest)
def on_friend_request_deleted(sender, instance, **kwargs):
    if instance.status == FriendRequest.STATUS_ACCEPTED:
        recount_friends(instance.sender_id, instance.receiver_id)
        graph_sync.friends_unlinked(instance.sender_id, instance.receiver_id)
