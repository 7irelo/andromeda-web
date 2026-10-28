"""
What moderation can act on, in one place.

For each content type: how to load it (object, author, text), whether a given
member may see it (you can only report what you can see), and how to apply a
moderation status. Everything else in moderation goes through here.
"""
from django.db.models import Q

from core import visibility

from .models import STATUS_REMOVED, ModerationCase as C

SNAPSHOT_CHARS = 4000


def load(content_type, object_id):
    """(object, author, text) for the content, or (None, None, '') if it no longer exists."""
    if content_type == C.TYPE_POST:
        from posts.models import Post
        obj = Post.objects.select_related('author').filter(pk=object_id).first()
        return obj, (obj.author if obj else None), (obj.content if obj else '')
    if content_type == C.TYPE_COMMENT:
        from posts.models import Comment
        obj = Comment.objects.select_related('author').filter(pk=object_id).first()
        return obj, (obj.author if obj else None), (obj.content if obj else '')
    if content_type == C.TYPE_LISTING:
        from marketplace.models import Listing
        obj = Listing.objects.select_related('seller').filter(pk=object_id).first()
        return obj, (obj.seller if obj else None), (f'{obj.title}\n{obj.description}' if obj else '')
    if content_type == C.TYPE_MESSAGE:
        from chats.models import Message
        obj = Message.objects.select_related('sender').filter(pk=object_id).first()
        text = (obj.content or obj.transcript or '') if obj else ''
        return obj, (obj.sender if obj else None), text
    if content_type == C.TYPE_USER:
        from django.contrib.auth import get_user_model
        obj = get_user_model().objects.filter(pk=object_id).first()
        return obj, obj, (f'@{obj.username} {obj.get_full_name()}\n{obj.bio}' if obj else '')
    if content_type == C.TYPE_VIDEO:
        from watch.models import Video
        obj = Video.objects.select_related('uploader').filter(pk=object_id).first()
        return obj, (obj.uploader if obj else None), (f'{obj.title}\n{obj.description}' if obj else '')
    raise ValueError(content_type)


def can_see(user, content_type, obj):
    """Whether `user` can currently see `obj` (and so may report it)."""
    if obj is None:
        return False
    if content_type == C.TYPE_POST:
        return visibility.can_view_post(user, obj)
    if content_type == C.TYPE_COMMENT:
        return obj.author_id not in visibility.blocked_ids(user) and visibility.can_view_post(user, obj.post)
    if content_type == C.TYPE_LISTING:
        from core.search import visible_listings
        return obj.seller_id == user.id or visible_listings(user).filter(pk=obj.pk).exists()
    if content_type == C.TYPE_MESSAGE:
        from chats.models import ChatMember
        return not obj.is_deleted and ChatMember.objects.filter(room_id=obj.room_id, user=user).exists()
    if content_type == C.TYPE_USER:
        # Blocking someone shouldn't stop you reporting them.
        return obj.is_active and obj.pk != user.pk
    if content_type == C.TYPE_VIDEO:
        from watch.access import visible_videos
        return visible_videos(user).filter(pk=obj.pk).exists()
    return False


def set_status(content_type, obj, status):
    """Apply a moderation status. Profiles and messages have no status field, so removal clears them."""
    if content_type in (C.TYPE_POST, C.TYPE_COMMENT, C.TYPE_LISTING, C.TYPE_VIDEO):
        type(obj).objects.filter(pk=obj.pk).update(moderation_status=status)
    elif content_type == C.TYPE_MESSAGE and status == STATUS_REMOVED:
        from chats.models import MessageReaction
        if obj.file:
            obj.file.delete(save=False)
        type(obj).objects.filter(pk=obj.pk).update(is_deleted=True, content='', transcript='', file=None)
        MessageReaction.objects.filter(message_id=obj.pk).delete()
    elif content_type == C.TYPE_USER and status == STATUS_REMOVED:
        # A removed profile loses its public text and pictures; the account itself is
        # handled with warn/suspend/ban.
        if obj.avatar:
            obj.avatar.delete(save=False)
        if obj.cover_photo:
            obj.cover_photo.delete(save=False)
        type(obj).objects.filter(pk=obj.pk).update(bio='', website='', avatar=None, cover_photo=None)


def removed_q():
    return Q(moderation_status=STATUS_REMOVED)
