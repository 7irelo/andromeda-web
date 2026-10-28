"""
Keep inboxes in step with the database. Everything runs after commit and is
best effort: a failure here only means a slower (database) feed read, never a
wrong one, because reads re-check visibility.
"""
import logging

from django.db import transaction
from django.db.models.signals import post_delete, post_init, post_save

from . import candidates

logger = logging.getLogger(__name__)


def _after_commit(fn, *args):
    if not candidates.enabled():
        return

    def run():
        try:
            fn(*args)
        except Exception:
            logger.warning('Feed cache update failed', exc_info=True)
    transaction.on_commit(run)


def _task(task, *args):
    _after_commit(task.delay, *args)


def _invalidate(*user_ids):
    _after_commit(candidates.invalidate, *user_ids)


def _remember_privacy(sender, instance, **kwargs):
    instance._feedcache_privacy = instance.privacy if 'privacy' in instance.__dict__ else None


def _post_saved(sender, instance, created, update_fields=None, **kwargs):
    from . import tasks

    if created:
        _task(tasks.fan_out_post, instance.id)
    elif getattr(instance, '_feedcache_privacy', None) not in (None, instance.privacy):
        _task(tasks.refresh_post, instance.id)
    instance._feedcache_privacy = instance.privacy


def _post_deleted(sender, instance, **kwargs):
    from . import tasks

    _task(tasks.retract_post, instance.id, instance.author_id, instance.group_id, instance.page_id)


def _block_changed(sender, instance, **kwargs):
    _invalidate(instance.blocker_id, instance.blocked_id)


def _friendship_changed(sender, instance, **kwargs):
    from users.models import FriendRequest

    # Saved as accepted = new friends; an accepted row deleted = unfriended.
    if instance.status == FriendRequest.STATUS_ACCEPTED:
        _invalidate(instance.sender_id, instance.receiver_id)


def _membership_changed(sender, instance, **kwargs):
    _invalidate(instance.user_id)


def _user_deleted(sender, instance, **kwargs):
    _invalidate(instance.id)


def connect():
    from groups.models import GroupMember
    from pages.models import PageFollow
    from posts.models import Post
    from users.models import Block, FriendRequest, User

    post_init.connect(_remember_privacy, sender=Post, dispatch_uid='feedcache-post-init')
    post_save.connect(_post_saved, sender=Post, dispatch_uid='feedcache-post-saved')
    post_delete.connect(_post_deleted, sender=Post, dispatch_uid='feedcache-post-deleted')
    for signal in (post_save, post_delete):
        signal.connect(_block_changed, sender=Block, dispatch_uid=f'feedcache-block-{id(signal)}')
        signal.connect(_friendship_changed, sender=FriendRequest, dispatch_uid=f'feedcache-friend-{id(signal)}')
        signal.connect(_membership_changed, sender=GroupMember, dispatch_uid=f'feedcache-member-{id(signal)}')
        signal.connect(_membership_changed, sender=PageFollow, dispatch_uid=f'feedcache-follow-{id(signal)}')
    post_delete.connect(_user_deleted, sender=User, dispatch_uid='feedcache-user-deleted')
