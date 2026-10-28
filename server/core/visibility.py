"""
Single source of truth for "who may see what".

Every read path (feed, profiles, groups, search and, later, AI retrieval) goes
through these helpers so privacy rules are enforced in exactly one place.
"""
from django.db.models import Exists, OuterRef, Q


def friend_ids(user):
    from users.models import FriendRequest

    if not user.is_authenticated:
        return set()
    rows = FriendRequest.objects.filter(
        Q(sender=user) | Q(receiver=user), status=FriendRequest.STATUS_ACCEPTED
    ).values_list('sender_id', 'receiver_id')
    return {s if r == user.id else r for s, r in rows}


def blocked_ids(user):
    """Users this user blocked or was blocked by. Blocks hide content both ways."""
    from users.models import Block

    if not user.is_authenticated:
        return set()
    rows = Block.objects.filter(Q(blocker=user) | Q(blocked=user)).values_list('blocker_id', 'blocked_id')
    return {b if a == user.id else a for a, b in rows}


def are_friends(a, b):
    return b.id in friend_ids(a)


def is_blocked(a, b):
    return b.id in blocked_ids(a)


def have_mutual_friend(a, b):
    return bool(friend_ids(a) & friend_ids(b))


def member_group_ids(user):
    from groups.models import GroupMember

    return GroupMember.objects.filter(user=user).values('group_id')


def visible_posts(user, qs=None):
    from groups.models import GroupBan
    from posts.models import Post

    qs = Post.objects.all() if qs is None else qs
    privacy = (
        Q(author=user)
        | Q(privacy=Post.PRIVACY_PUBLIC)
        | Q(privacy=Post.PRIVACY_FRIENDS, author_id__in=friend_ids(user))
    )
    group = Q(group__isnull=True) | Q(group__privacy='public') | Q(group_id__in=member_group_ids(user))
    moderation = Q(author=user) | ~Q(moderation_status='removed')
    # A user banned from a group loses their posts in it as well as their seat.
    banned = GroupBan.objects.filter(group_id=OuterRef('group_id'), user_id=OuterRef('author_id'))
    return qs.filter(privacy & group & moderation & ~Exists(banned)).exclude(author_id__in=blocked_ids(user))


def can_view_post(user, post):
    return visible_posts(user).filter(pk=post.pk).exists()


def visible_groups(user, qs=None):
    """
    Public and private groups are discoverable; secret groups only by members.
    (Invite-link holders see a secret group's card through the invite preview,
    never through lists, search or suggestions.)
    """
    from groups.models import Group

    qs = Group.objects.all() if qs is None else qs
    return qs.filter(~Q(privacy=Group.PRIVACY_SECRET) | Q(id__in=member_group_ids(user)))


def can_view_group_content(user, group):
    return group.privacy == 'public' or group.memberships.filter(user=user).exists()


def _audience_allows(viewer, target, setting):
    if viewer.id == target.id:
        return True
    if is_blocked(viewer, target):
        return False
    if setting == 'everyone':
        return True
    if setting == 'friends':
        return are_friends(viewer, target)
    if setting == 'friends_of_friends':
        return are_friends(viewer, target) or have_mutual_friend(viewer, target)
    return False  # 'private' / 'nobody'


def can_view_profile(viewer, target):
    return _audience_allows(viewer, target, target.privacy_profile)


def can_view_friends_list(viewer, target):
    return _audience_allows(viewer, target, target.privacy_friends_list)


def can_message(sender, recipient):
    return _audience_allows(sender, recipient, recipient.privacy_messages)


def can_send_friend_request(sender, recipient):
    return sender.id != recipient.id and _audience_allows(
        sender, recipient, recipient.privacy_friend_requests
    )
