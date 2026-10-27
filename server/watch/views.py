from django.db.models import F, Q
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from core import visibility
from core.permissions import IsOwnerOrReadOnly
from .models import Video, VideoLike, VideoView
from .serializers import VideoSerializer, VideoCommentSerializer


class VideoViewSet(viewsets.ModelViewSet):
    serializer_class = VideoSerializer
    permission_classes = [IsOwnerOrReadOnly]
    owner_field = 'uploader'
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        qs = Video.objects.filter(
            Q(status=Video.STATUS_READY, is_public=True) | Q(uploader=user)
        ).exclude(uploader_id__in=visibility.blocked_ids(user)).select_related('uploader')
        uploader = self.request.query_params.get('uploader')
        if uploader:
            qs = qs.filter(uploader_id=uploader)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(title__icontains=search.strip()[:100])
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        instance = serializer.save(uploader=self.request.user)
        instance.status = Video.STATUS_READY
        instance.save(update_fields=['status'])

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Count one view per user per video, atomically.
        if instance.uploader_id != request.user.id:
            if not VideoView.objects.filter(video=instance, user=request.user).exists():
                VideoView.objects.create(video=instance, user=request.user)
                Video.objects.filter(pk=instance.pk).update(views_count=F('views_count') + 1)
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def like(self, request, pk=None):
        video = self.get_object()
        like, created = VideoLike.objects.get_or_create(user=request.user, video=video)
        if not created:
            like.delete()
            Video.objects.filter(pk=video.pk).update(likes_count=video.likes.count())
            return Response({'liked': False})
        Video.objects.filter(pk=video.pk).update(likes_count=video.likes.count())
        return Response({'liked': True})

    @action(detail=True, methods=['get', 'post'])
    def comments(self, request, pk=None):
        video = self.get_object()
        if request.method == 'GET':
            comments = video.comments.filter(parent=None).exclude(
                author_id__in=visibility.blocked_ids(request.user)).select_related('author')[:200]
            return Response(VideoCommentSerializer(comments, many=True, context={'request': request}).data)
        serializer = VideoCommentSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        parent = serializer.validated_data.get('parent')
        if parent is not None and parent.video_id != video.id:
            return Response({'parent': ['Replies must belong to the same video.']}, status=400)
        serializer.save(author=request.user, video=video)
        Video.objects.filter(pk=video.pk).update(comments_count=video.comments.count())
        return Response(serializer.data, status=201)
