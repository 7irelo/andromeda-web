import logging

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from core import visibility
from core.permissions import IsPageAdminOrReadOnly, is_page_admin
from users.serializers import UserSerializer
from .models import Page, PageAdmin, PageFollow
from .serializers import PageAdminSerializer, PageSerializer

logger = logging.getLogger(__name__)

ALL_ROLES = tuple(role for role, _label in PageAdmin.ROLE_CHOICES)


def _id_param(request, name):
    value = request.data.get(name)
    if isinstance(value, bool) or not str(value).isdigit():
        raise ValidationError({name: 'A numeric id is required.'})
    return int(value)


def _admin_ids(page):
    """Everyone with full admin rights: admin-role holders plus the creator."""
    ids = set(page.admins.filter(role=PageAdmin.ROLE_ADMIN).values_list('user_id', flat=True))
    if page.created_by_id:
        ids.add(page.created_by_id)
    return ids


class PageViewSet(viewsets.ModelViewSet):
    serializer_class = PageSerializer
    permission_classes = [IsPageAdminOrReadOnly]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        qs = Page.objects.select_related('created_by')
        search = self.request.query_params.get('search', '').strip()[:100]
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    def perform_create(self, serializer):
        page = serializer.save(created_by=self.request.user)
        PageAdmin.objects.create(page=page, user=self.request.user, role=PageAdmin.ROLE_ADMIN)

    @action(detail=True, methods=['post'])
    def follow(self, request, pk=None):
        page = self.get_object()
        _, created = PageFollow.objects.get_or_create(page=page, user=request.user)
        Page.objects.filter(pk=page.pk).update(followers_count=page.followers.count())
        return Response({'following': True, 'created': created})

    @action(detail=True, methods=['post'])
    def unfollow(self, request, pk=None):
        page = self.get_object()
        PageFollow.objects.filter(page=page, user=request.user).delete()
        Page.objects.filter(pk=page.pk).update(followers_count=page.followers.count())
        return Response({'following': False})

    @action(detail=True, methods=['get'])
    def followers(self, request, pk=None):
        page = self.get_object()
        follows = page.followers.filter(user__is_active=True).exclude(
            user_id__in=visibility.blocked_ids(request.user)
        ).select_related('user').order_by('-created_at')
        result = self.paginate_queryset(follows)
        return self.get_paginated_response(
            UserSerializer([f.user for f in result], many=True, context={'request': request}).data
        )

    # ── Roles ──────────────────────────────────────────────────

    @action(detail=True, methods=['get', 'post'])
    def admins(self, request, pk=None):
        """
        ``GET``: the page's team, visible to anyone on it. ``POST`` ``{user_id, role}``:
        add someone or change their role (admins only).
        """
        page = self.get_object()
        if request.method == 'GET':
            if not is_page_admin(request.user, page, roles=ALL_ROLES):
                raise PermissionDenied('Only the page team can see its roles.')
            roles = page.admins.select_related('user').exclude(user_id__in=visibility.blocked_ids(request.user))
            return Response(PageAdminSerializer(roles, many=True, context={'request': request}).data)

        if not is_page_admin(request.user, page):
            raise PermissionDenied('Only page admins can manage roles.')
        role = request.data.get('role')
        if role not in ALL_ROLES:
            raise ValidationError({'role': f'Choose one of: {", ".join(ALL_ROLES)}.'})
        user = get_object_or_404(get_user_model(), pk=_id_param(request, 'user_id'), is_active=True)
        if visibility.is_blocked(request.user, user):
            raise PermissionDenied('You cannot add this user.')
        if user.id == page.created_by_id:
            raise ValidationError({'detail': "The page's creator is always an admin."})
        if role != PageAdmin.ROLE_ADMIN and not (_admin_ids(page) - {user.id}):
            raise ValidationError({'detail': 'Make someone else an admin first.'})
        membership, created = PageAdmin.objects.get_or_create(page=page, user=user, defaults={'role': role})
        changed = created or membership.role != role
        if changed:
            membership.role = role
            membership.save(update_fields=['role'])
            self._notify_role(page, user, role)
        return Response(PageAdminSerializer(membership, context={'request': request}).data,
                        status=201 if created else 200)

    @action(detail=True, methods=['post'], url_path='admins/remove')
    def remove_admin(self, request, pk=None):
        """Admins can remove anyone from the team; anyone on it can remove themselves."""
        page = self.get_object()
        user_id = _id_param(request, 'user_id')
        if user_id != request.user.id and not is_page_admin(request.user, page):
            raise PermissionDenied('Only page admins can manage roles.')
        membership = get_object_or_404(page.admins, user_id=user_id)
        if user_id == page.created_by_id:
            raise ValidationError({'detail': "The page's creator can't be removed."})
        if not (_admin_ids(page) - {user_id}):
            raise ValidationError({'detail': 'Make someone else an admin first.'})
        membership.delete()
        return Response({'status': 'removed'})

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def verify(self, request, pk=None):
        """Staff only. Page admins can't verify their own page through the normal edit."""
        page = self.get_object()
        value = request.data.get('is_verified', True)
        if not isinstance(value, bool):
            value = str(value).lower() in ('true', '1')
        Page.objects.filter(pk=page.pk).update(is_verified=value)
        return Response({'is_verified': value})

    def _notify_role(self, page, user, role):
        from notifications.models import Notification

        try:
            Notification.objects.create(
                recipient=user, sender=self.request.user, notification_type=Notification.TYPE_SYSTEM,
                title=f'You are now an {role} of {page.name}'[:255],  # admin / editor / analyst
                extra={'kind': 'page_role', 'page_id': page.id, 'role': role},
            )
        except Exception:
            logger.warning('Page role notification failed', exc_info=True)
