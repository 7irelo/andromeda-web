from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.permissions import IsPageAdminOrReadOnly
from .models import Page, PageAdmin, PageFollow
from .serializers import PageSerializer


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
