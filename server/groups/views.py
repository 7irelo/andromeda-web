from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from core import visibility
from core.permissions import IsGroupAdminOrReadOnly
from .models import Group, GroupJoinRequest, GroupMember
from .serializers import GroupJoinRequestSerializer, GroupMemberSerializer, GroupSerializer


def _recount(group):
    Group.objects.filter(pk=group.pk).update(members_count=group.memberships.count())


def _role(group, user):
    m = group.memberships.filter(user=user).first()
    return m.role if m else None


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

    # ── Admin / moderator actions ──────────────────────────────

    def _require_role(self, group, roles=(GroupMember.ROLE_ADMIN, GroupMember.ROLE_MODERATOR)):
        if _role(group, self.request.user) not in roles:
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
        with transaction.atomic():
            if decision == 'approve':
                GroupMember.objects.get_or_create(group=group, user=jr.user)
                jr.delete()
                _recount(group)
            else:
                jr.delete()
        return Response({'status': decision + 'd'})

    @action(detail=True, methods=['post'])
    def invite(self, request, pk=None):
        """Members of private/secret groups can be added directly by admins."""
        from django.contrib.auth import get_user_model
        group = self.get_object()
        self._require_role(group, (GroupMember.ROLE_ADMIN,))
        user = get_object_or_404(get_user_model(), pk=request.data.get('user_id'), is_active=True)
        if visibility.is_blocked(request.user, user):
            raise PermissionDenied('You cannot add this user.')
        GroupMember.objects.get_or_create(group=group, user=user)
        GroupJoinRequest.objects.filter(group=group, user=user).delete()
        _recount(group)
        return Response({'status': 'added'})

    @action(detail=True, methods=['post'])
    def set_role(self, request, pk=None):
        group = self.get_object()
        self._require_role(group, (GroupMember.ROLE_ADMIN,))
        role = request.data.get('role')
        if role not in dict(GroupMember.ROLE_CHOICES):
            raise ValidationError({'role': 'Invalid role.'})
        membership = get_object_or_404(group.memberships, user_id=request.data.get('user_id'))
        if membership.user_id == request.user.id:
            raise ValidationError({'detail': 'You cannot change your own role.'})
        membership.role = role
        membership.save(update_fields=['role'])
        return Response({'status': 'updated'})

    @action(detail=True, methods=['post'])
    def remove_member(self, request, pk=None):
        group = self.get_object()
        self._require_role(group)
        membership = get_object_or_404(group.memberships, user_id=request.data.get('user_id'))
        actor_is_admin = _role(group, request.user) == GroupMember.ROLE_ADMIN
        # Nobody removes themselves here (use leave); moderators can only remove plain members.
        if membership.user_id == request.user.id or (
            not actor_is_admin and membership.role != GroupMember.ROLE_MEMBER
        ):
            raise PermissionDenied('You cannot remove this member.')
        membership.delete()
        _recount(group)
        return Response({'status': 'removed'})
