from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Group, GroupMember
from .serializers import GroupSerializer, GroupMemberSerializer


class GroupViewSet(viewsets.ModelViewSet):
    serializer_class = GroupSerializer
    queryset = Group.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        mine = self.request.query_params.get('mine')
        if mine == 'true':
            qs = qs.filter(memberships__user=self.request.user)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(name__icontains=search)
        return qs.select_related('created_by')

    def perform_create(self, serializer):
        group = serializer.save(created_by=self.request.user)
        GroupMember.objects.create(group=group, user=self.request.user, role=GroupMember.ROLE_ADMIN)
        Group.objects.filter(pk=group.pk).update(members_count=1)

    @action(detail=True, methods=['post'])
    def join(self, request, pk=None):
        group = self.get_object()
        if group.memberships.filter(user=request.user).exists():
            return Response({'detail': 'Already a member.'}, status=400)
        if group.privacy == Group.PRIVACY_PUBLIC:
            GroupMember.objects.create(group=group, user=request.user)
            Group.objects.filter(pk=group.pk).update(members_count=group.memberships.count())
            return Response({'status': 'joined'})
        return Response({'status': 'request_pending'})

    @action(detail=True, methods=['post'])
    def leave(self, request, pk=None):
        group = self.get_object()
        group.memberships.filter(user=request.user).delete()
        Group.objects.filter(pk=group.pk).update(members_count=group.memberships.count())
        return Response({'status': 'left'})

    @action(detail=True, methods=['get'])
    def members(self, request, pk=None):
        group = self.get_object()
        members = group.memberships.select_related('user').all()
        return Response(GroupMemberSerializer(members, many=True, context={'request': request}).data)
