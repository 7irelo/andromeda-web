from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Video, VideoLike, VideoView, VideoComment
from .serializers import VideoSerializer, VideoCommentSerializer


class VideoViewSet(viewsets.ModelViewSet):
    serializer_class = VideoSerializer

    def get_queryset(self):
        qs = Video.objects.filter(status=Video.STATUS_READY, is_public=True).select_related('uploader')
        uploader = self.request.query_params.get('uploader')
        if uploader:
            qs = qs.filter(uploader_id=uploader)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(title__icontains=search)
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(uploader=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        Video.objects.filter(pk=instance.pk).update(views_count=instance.views_count + 1)
        VideoView.objects.create(
            video=instance,
            user=request.user if request.user.is_authenticated else None,
        )
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
            comments = video.comments.filter(parent=None).select_related('author')
            return Response(VideoCommentSerializer(comments, many=True, context={'request': request}).data)
        serializer = VideoCommentSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save(author=request.user, video=video)
        Video.objects.filter(pk=video.pk).update(comments_count=video.comments.count())
        return Response(serializer.data, status=201)
