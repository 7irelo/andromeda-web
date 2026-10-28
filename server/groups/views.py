import hmac
import logging
import re
import secrets

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from core import visibility
from core.permissions import IsGroupAdminOrReadOnly
from .models import Group, GroupBan, GroupInvite, GroupJoinRequest, GroupMember, GroupPinnedPost, GroupRule
from .serializers import (
    GroupBanSerializer, GroupInviteCreateSerializer, GroupInvitePreviewSerializer, GroupInviteSerializer,
    GroupJoinRequestSerializer, GroupMemberSerializer, GroupRuleSerializer, GroupRulesUpdateSerializer,
    GroupSerializer,
)

logger = logging.getLogger(__name__)

MAX_PINNED_POSTS = 3
MAX_ACTIVE_INVITES = 100
ADMIN_ROLES = (GroupMember.ROLE_ADMIN,)
MODERATOR_ROLES = (GroupMember.ROLE_ADMIN, GroupMember.ROLE_MODERATOR)


def _recount(group):
    Group.objects.filter(pk=group.pk).update(members_count=group.memberships.count())


def _role(group, user):
    m = group.memberships.filter(user=user).first()
    return m.role if m else None


def _is_banned(group, user):
    return group.bans.filter(user=user).exists()


def _id_param(request, name):
    value = request.data.get(name)
    if isinstance(value, bool) or not str(value).isdigit():
        raise ValidationError({name: 'A numeric id is required.'})
    return int(value)


def _notify(recipient, sender, kind, title, notification_type=None, **extra):
    """Best effort: a notification failure never undoes the membership change."""
    from notifications.models import Notification

    try:
        Notification.objects.create(
            recipient=recipient, sender=sender,
            notification_type=notification_type or Notification.TYPE_SYSTEM,
            title=title[:255], extra={'kind': kind, **extra},
        )
    except Exception:
        logger.warning('Group notification failed', exc_info=True)


class GroupViewSet(viewsets.ModelViewSet):
    serializer_class = GroupSerializer
    permission_classes = [IsGroupAdminOrReadOnly]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        qs = visibility.visible_groups(self.request.user)
        if self.request.query_params.get('mine') == 'true':
            qs = qs.filter(memberships__user=self.request.user)
        search = self.request.query_params.get('search', '').strip()[:100]
        if search:
            qs = qs.filter(name__icontains=search)
        return qs.select_related('created_by')

    def perform_create(self, serializer):
        with transaction.atomic():
            group = serializer.save(created_by=self.request.user)
            GroupMember.objects.create(group=group, user=self.request.user, role=GroupMember.ROLE_ADMIN)
            Group.objects.filter(pk=group.pk).update(members_count=1)

    @action(detail=True, methods=['post'])
    def join(self, request, pk=None):
        group = self.get_object()
        if group.memberships.filter(user=request.user).exists():
            raise ValidationError({'detail': 'Already a member.'})
        if _is_banned(group, request.user):
            raise PermissionDenied('You are banned from this group.')
        if group.privacy == Group.PRIVACY_PUBLIC:
            GroupMember.objects.create(group=group, user=request.user)
            _recount(group)
            return Response({'status': 'joined'})
        if group.privacy == Group.PRIVACY_SECRET:
            raise PermissionDenied('Secret groups are invite-only.')
        GroupJoinRequest.objects.get_or_create(
            group=group, user=request.user, defaults={'status': GroupJoinRequest.STATUS_PENDING}
        )
        return Response({'status': 'request_pending'})

    @action(detail=True, methods=['post'])
    def leave(self, request, pk=None):
        group = self.get_object()
        membership = group.memberships.filter(user=request.user).first()
        if membership is None:
            raise ValidationError({'detail': 'You are not a member.'})
        if membership.role == GroupMember.ROLE_ADMIN and not group.memberships.filter(
            role=GroupMember.ROLE_ADMIN
        ).exclude(user=request.user).exists() and group.memberships.count() > 1:
            raise ValidationError({'detail': 'Make someone else an admin before leaving.'})
        membership.delete()
        _recount(group)
        return Response({'status': 'left'})

    @action(detail=True, methods=['get'])
    def members(self, request, pk=None):
        group = self.get_object()
        if not visibility.can_view_group_content(request.user, group):
            raise PermissionDenied('Join this group to see its members.')
        members = group.memberships.select_related('user').exclude(
            user_id__in=visibility.blocked_ids(request.user)
        )
        page = self.paginate_queryset(members)
        return self.get_paginated_response(
            GroupMemberSerializer(page, many=True, context={'request': request}).data
        )

    @action(detail=True, methods=['get', 'post'])
    def rules(self, request, pk=None):
        """Anyone who can see the group can read its rules: they are shown before joining."""
        group = self.get_object()
        if request.method == 'POST':
            self._require_role(group, ADMIN_ROLES)
            serializer = GroupRulesUpdateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            with transaction.atomic():
                group.rules.all().delete()
                GroupRule.objects.bulk_create([
                    GroupRule(group=group, position=i, title=r['title'].strip(), description=r['description'])
                    for i, r in enumerate(serializer.validated_data['rules'])
                ])
        return Response(GroupRuleSerializer(group.rules.all(), many=True).data)

    @action(detail=True, methods=['get'])
    def pinned(self, request, pk=None):
        """Pinned posts, newest pin first. The client shows these above the group feed."""
        from posts.serializers import PostSerializer

        group = self.get_object()
        if not visibility.can_view_group_content(request.user, group):
            raise PermissionDenied('Join this group to see its posts.')
        posts = visibility.visible_posts(request.user).filter(
            group=group, group_pins__group=group
        ).select_related('author', 'shared_post__author', 'group').prefetch_related(
            'media', 'tags'
        ).order_by('-group_pins__pinned_at')[:MAX_PINNED_POSTS]
        return Response(PostSerializer(posts, many=True, context={'request': request}).data)

    # ── Admin / moderator actions ──────────────────────────────

    def _require_role(self, group, roles=MODERATOR_ROLES):
        if _role(group, self.request.user) not in roles:
            if roles == ADMIN_ROLES:
                raise PermissionDenied('You need to be a group admin.')
            raise PermissionDenied('You need to be a group admin or moderator.')

    @action(detail=True, methods=['get'])
    def join_requests(self, request, pk=None):
        group = self.get_object()
        self._require_role(group)
        reqs = group.join_requests.filter(status=GroupJoinRequest.STATUS_PENDING).select_related('user')
        return Response(GroupJoinRequestSerializer(reqs, many=True, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path=r'join_requests/(?P<request_id>\d+)/(?P<decision>approve|decline)')
    def decide_join_request(self, request, pk=None, request_id=None, decision=None):
        group = self.get_object()
        self._require_role(group)
        jr = get_object_or_404(group.join_requests, pk=request_id, status=GroupJoinRequest.STATUS_PENDING)
        if decision == 'approve' and _is_banned(group, jr.user):
            jr.delete()
            raise PermissionDenied('This user is banned from the group.')
        with transaction.atomic():
            if decision == 'approve':
                GroupMember.objects.get_or_create(group=group, user=jr.user)
                jr.delete()
                _recount(group)
            else:
                jr.delete()
        if decision == 'approve':
            _notify(jr.user, request.user, 'group_join_approved',
                    f'Your request to join {group.name} was approved', group_id=group.id)
        return Response({'status': decision + 'd'})

    @action(detail=True, methods=['post'])
    def invite(self, request, pk=None):
        """Members of private/secret groups can be added directly by admins."""
        group = self.get_object()
        self._require_role(group, ADMIN_ROLES)
        user = get_object_or_404(get_user_model(), pk=_id_param(request, 'user_id'), is_active=True)
        if visibility.is_blocked(request.user, user):
            raise PermissionDenied('You cannot add this user.')
        if _is_banned(group, user):
            raise PermissionDenied('Unban this user before adding them.')
        _, created = GroupMember.objects.get_or_create(group=group, user=user)
        GroupJoinRequest.objects.filter(group=group, user=user).delete()
        _recount(group)
        if created:
            from notifications.models import Notification
            _notify(user, request.user, 'group_added', f'You were added to {group.name}',
                    notification_type=Notification.TYPE_GROUP_INVITE, group_id=group.id)
        return Response({'status': 'added'})

    @action(detail=True, methods=['post'])
    def set_role(self, request, pk=None):
        group = self.get_object()
        self._require_role(group, ADMIN_ROLES)
        role = request.data.get('role')
        if role not in dict(GroupMember.ROLE_CHOICES):
            raise ValidationError({'role': 'Invalid role.'})
        membership = get_object_or_404(group.memberships, user_id=_id_param(request, 'user_id'))
        # An admin may step down, but only once someone else is an admin.
        if membership.user_id == request.user.id and role != GroupMember.ROLE_ADMIN and not group.memberships.filter(
            role=GroupMember.ROLE_ADMIN
        ).exclude(user=request.user).exists():
            raise ValidationError({'detail': 'Make someone else an admin before stepping down.'})
        membership.role = role
        membership.save(update_fields=['role'])
        return Response({'status': 'updated'})

    @action(detail=True, methods=['post'])
    def remove_member(self, request, pk=None):
        """Kick: the user can rejoin (or ask to) later. Use ``ban`` to keep them out."""
        group = self.get_object()
        self._require_role(group)
        membership = get_object_or_404(group.memberships, user_id=_id_param(request, 'user_id'))
        actor_is_admin = _role(group, request.user) == GroupMember.ROLE_ADMIN
        # Nobody removes themselves here (use leave); moderators can only remove plain members.
        if membership.user_id == request.user.id or (
            not actor_is_admin and membership.role != GroupMember.ROLE_MEMBER
        ):
            raise PermissionDenied('You cannot remove this member.')
        membership.delete()
        _recount(group)
        return Response({'status': 'removed'})

    @action(detail=True, methods=['get'])
    def bans(self, request, pk=None):
        group = self.get_object()
        self._require_role(group, ADMIN_ROLES)
        bans = group.bans.select_related('user').exclude(user_id__in=visibility.blocked_ids(request.user))
        page = self.paginate_queryset(bans)
        return self.get_paginated_response(GroupBanSerializer(page, many=True, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def ban(self, request, pk=None):
        group = self.get_object()
        self._require_role(group, ADMIN_ROLES)
        user = get_object_or_404(get_user_model(), pk=_id_param(request, 'user_id'))
        if user.id == request.user.id:
            raise ValidationError({'detail': 'You cannot ban yourself.'})
        if _role(group, user) == GroupMember.ROLE_ADMIN:
            raise PermissionDenied('Demote this admin before banning them.')
        reason = str(request.data.get('reason', '')).strip()[:255]
        with transaction.atomic():
            group.memberships.filter(user=user).delete()
            group.join_requests.filter(user=user).delete()
            GroupBan.objects.update_or_create(
                group=group, user=user, defaults={'banned_by': request.user, 'reason': reason}
            )
            _recount(group)
        return Response({'status': 'banned'})

    @action(detail=True, methods=['post'])
    def unban(self, request, pk=None):
        group = self.get_object()
        self._require_role(group, ADMIN_ROLES)
        deleted, _ = group.bans.filter(user_id=_id_param(request, 'user_id')).delete()
        if not deleted:
            raise NotFound('This user is not banned.')
        return Response({'status': 'unbanned'})

    @action(detail=True, methods=['post'])
    def remove_post(self, request, pk=None):
        from posts.models import Post

        group = self.get_object()
        self._require_role(group)
        post = get_object_or_404(Post, pk=_id_param(request, 'post_id'), group=group)
        self._check_can_moderate(group, post.author)
        post.delete()
        return Response({'status': 'removed'})

    @action(detail=True, methods=['post'])
    def remove_comment(self, request, pk=None):
        from posts.models import Comment

        group = self.get_object()
        self._require_role(group)
        comment = get_object_or_404(Comment, pk=_id_param(request, 'comment_id'), post__group=group)
        self._check_can_moderate(group, comment.author)
        comment.delete()
        return Response({'status': 'removed'})

    def _check_can_moderate(self, group, author):
        # Moderators can't remove content written by admins.
        if _role(group, self.request.user) != GroupMember.ROLE_ADMIN and _role(group, author) == GroupMember.ROLE_ADMIN:
            raise PermissionDenied('Moderators cannot remove content posted by an admin.')

    @action(detail=True, methods=['post'])
    def pin(self, request, pk=None):
        group = self.get_object()
        self._require_role(group)
        post = get_object_or_404(
            visibility.visible_posts(request.user).filter(group=group), pk=_id_param(request, 'post_id')
        )
        with transaction.atomic():
            Group.objects.select_for_update().filter(pk=group.pk).first()  # serialise concurrent pins
            if group.pins.filter(post=post).exists():
                return Response({'status': 'pinned'})
            if group.pins.count() >= MAX_PINNED_POSTS:
                raise ValidationError({'detail': f'A group can pin at most {MAX_PINNED_POSTS} posts.'})
            GroupPinnedPost.objects.create(group=group, post=post, pinned_by=request.user)
        return Response({'status': 'pinned'})

    @action(detail=True, methods=['post'])
    def unpin(self, request, pk=None):
        group = self.get_object()
        self._require_role(group)
        group.pins.filter(post_id=_id_param(request, 'post_id')).delete()
        return Response({'status': 'unpinned'})

    @action(detail=True, methods=['get', 'post'])
    def invites(self, request, pk=None):
        """Invite links. The raw token appears once, in the create response."""
        group = self.get_object()
        self._require_role(group)
        if request.method == 'GET':
            invites = group.invites.select_related('created_by')[:50]
            return Response(GroupInviteSerializer(invites, many=True, context={'request': request}).data)
        serializer = GroupInviteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        active = group.invites.filter(revoked_at__isnull=True, expires_at__gt=timezone.now()).count()
        if active >= MAX_ACTIVE_INVITES:
            raise ValidationError({'detail': 'Revoke some invite links before creating more.'})
        token = secrets.token_urlsafe(32)
        invite = GroupInvite.objects.create(
            group=group, created_by=request.user, token_hash=GroupInvite.hash_token(token),
            expires_at=serializer.expires_at(), max_uses=serializer.validated_data.get('max_uses'),
        )
        data = GroupInviteSerializer(invite, context={'request': request}).data
        data['token'] = token
        return Response(data, status=201)

    @action(detail=True, methods=['post'], url_path=r'invites/(?P<invite_id>\d+)/revoke')
    def revoke_invite(self, request, pk=None, invite_id=None):
        group = self.get_object()
        self._require_role(group)
        invite = get_object_or_404(group.invites, pk=invite_id)
        if invite.revoked_at is None:
            invite.revoked_at = timezone.now()
            invite.save(update_fields=['revoked_at'])
        return Response({'status': 'revoked'})


# ── Invite links ──────────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(r'^[A-Za-z0-9_-]{20,128}$')
INVALID_INVITE = 'This invite link is invalid or has expired.'


class GroupInviteThrottle(UserRateThrottle):
    """Caps invite lookups and redemptions per user, on top of the global rates."""

    scope = 'group_invite'


def _find_invite(token, lock=False):
    """The usable invite for ``token``, or None. Unknown, expired and revoked look the same."""
    if not _TOKEN_RE.match(token or ''):
        return None
    digest = GroupInvite.hash_token(token)
    qs = GroupInvite.objects.select_related('group', 'created_by')
    if lock:
        qs = qs.select_for_update(of=('self',))
    invite = qs.filter(token_hash=digest).first()
    # The indexed lookup only reveals digests; compare_digest keeps the final check constant-time.
    if invite is None or not hmac.compare_digest(invite.token_hash, digest) or not invite.is_usable:
        return None
    return invite


class GroupInviteView(APIView):
    """
    ``GET`` previews the group behind an invite (this is how a secret group is
    discovered by someone holding a link); ``POST`` joins it.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [*api_settings.DEFAULT_THROTTLE_CLASSES, GroupInviteThrottle]

    def _check_allowed(self, invite, user):
        if _is_banned(invite.group, user):
            raise PermissionDenied('You are banned from this group.')
        if invite.created_by_id and visibility.is_blocked(user, invite.created_by):
            raise NotFound(INVALID_INVITE)

    def get(self, request, token):
        invite = _find_invite(token)
        if invite is None:
            raise NotFound(INVALID_INVITE)
        self._check_allowed(invite, request.user)
        group = invite.group
        return Response({
            'group': GroupInvitePreviewSerializer(group, context={'request': request}).data,
            'is_member': group.memberships.filter(user=request.user).exists(),
            'expires_at': invite.expires_at,
        })

    def post(self, request, token):
        with transaction.atomic():
            invite = _find_invite(token, lock=True)
            if invite is None:
                raise NotFound(INVALID_INVITE)
            self._check_allowed(invite, request.user)
            group = invite.group
            if group.memberships.filter(user=request.user).exists():
                return Response({'status': 'already_member', 'group_id': group.id})
            GroupMember.objects.create(group=group, user=request.user)
            GroupJoinRequest.objects.filter(group=group, user=request.user).delete()
            GroupInvite.objects.filter(pk=invite.pk).update(uses_count=F('uses_count') + 1)
            _recount(group)
        return Response({'status': 'joined', 'group_id': group.id})
