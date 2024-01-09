from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Page, PageFollow
from .serializers import PageSerializer


class PageViewSet(viewsets.ModelViewSet):
    serializer_class = PageSerializer
    queryset = Page.objects.all()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

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
