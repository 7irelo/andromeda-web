import math
from pathlib import PurePosixPath

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_safe
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, Throttled, ValidationError
from rest_framework.response import Response
from core import visibility
from core.permissions import IsOwnerOrReadOnly
from users.serializers import UserSerializer
from .access import ASSET_PATH_RE, CONTENT_TYPES, asset_key, read_stream_token, visible_videos
from .models import ChannelSubscription, Video, VideoLike, VideoView, WatchProgress
from .serializers import (VideoCommentSerializer, VideoDetailSerializer, VideoSerializer, WatchHistorySerializer,
                          WatchProgressSerializer)
from .tasks import queue_processing, relocate_assets

User = get_user_model()


def _int_param(request, name):
    value = request.query_params.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        raise ValidationError({name: 'Must be an integer.'}) from None


class VideoViewSet(viewsets.ModelViewSet):
    serializer_class = VideoSerializer
    permission_classes = [IsOwnerOrReadOnly]
    owner_field = 'uploader'
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_serializer_class(self):
        return VideoDetailSerializer if self.action == 'retrieve' else VideoSerializer

    def get_queryset(self):
        qs = visible_videos(self.request.user).select_related('uploader')
        uploader = _int_param(self.request, 'uploader')
        if uploader is not None:
            qs = qs.filter(uploader_id=uploader)
        if self.request.query_params.get('feed') == 'subscriptions':
            qs = qs.filter(uploader_id__in=ChannelSubscription.objects.filter(
                subscriber=self.request.user).values('channel_id'))
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(title__icontains=search.strip()[:100])
        return qs.order_by('-created_at')

    def _ready_object(self):
        video = self.get_object()
        if video.status != Video.STATUS_READY:
            raise ValidationError({'detail': 'This video is still processing.'})
        return video

    def perform_create(self, serializer):
        user = self.request.user
        busy = Video.objects.filter(uploader=user, status=Video.STATUS_PROCESSING).count()
        if busy >= settings.WATCH_MAX_PROCESSING_PER_USER:
            raise Throttled(detail='Wait for your other uploads to finish processing.')
        instance = serializer.save(uploader=user, status=Video.STATUS_PROCESSING)
        queue_processing(instance.pk)

    def perform_update(self, serializer):
        was_public = serializer.instance.is_public
        instance = serializer.save()
        if instance.is_public != was_public and instance.asset_files:
            transaction.on_commit(lambda: relocate_assets.delay(instance.pk))

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # One view per viewer, counted atomically; the unique constraint settles races.
        if instance.uploader_id != request.user.id and instance.status == Video.STATUS_READY:
            try:
                with transaction.atomic():
                    _, created = VideoView.objects.get_or_create(video=instance, user=request.user)
            except IntegrityError:
                created = False
            if created:
                Video.objects.filter(pk=instance.pk).update(views_count=F('views_count') + 1)
                instance.refresh_from_db(fields=['views_count'])
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        video = self.get_object()
        if video.uploader_id != request.user.id:
            raise PermissionDenied('You can only retry your own uploads.')
        if video.status != Video.STATUS_FAILED:
            raise ValidationError({'detail': 'Only failed uploads can be retried.'})
        Video.objects.filter(pk=video.pk).update(status=Video.STATUS_PROCESSING, failure_reason='',
                                                 processing_started_at=None)
        queue_processing(video.pk)
        return Response({'status': Video.STATUS_PROCESSING})

    @action(detail=True, methods=['post'])
    def like(self, request, pk=None):
        video = self._ready_object()
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
        if video.status != Video.STATUS_READY:
            raise ValidationError({'detail': 'This video is still processing.'})
        serializer = VideoCommentSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        parent = serializer.validated_data.get('parent')
        if parent is not None and parent.video_id != video.id:
            return Response({'parent': ['Replies must belong to the same video.']}, status=400)
        serializer.save(author=request.user, video=video)
        Video.objects.filter(pk=video.pk).update(comments_count=video.comments.count())
        return Response(serializer.data, status=201)

    @action(detail=True, methods=['get'])
    def captions(self, request, pk=None):
        """WebVTT captions, under the same visibility rules as the video."""
        video = self.get_object()
        if not video.captions_vtt:
            raise NotFound('This video has no captions.')
        response = HttpResponse(video.captions_vtt, content_type='text/vtt; charset=utf-8')
        response['X-Content-Type-Options'] = 'nosniff'
        response['Content-Security-Policy'] = "default-src 'none'; sandbox"
        response['Cache-Control'] = 'private, no-store'
        return response

    @action(detail=True, methods=['get'])
    def transcript(self, request, pk=None):
        video = self.get_object()
        if not video.transcript:
            raise NotFound('This video has no transcript.')
        return Response({'transcript': video.transcript, 'language': video.transcript_language})

    @action(detail=True, methods=['get', 'post'])
    def progress(self, request, pk=None):
        video = self._ready_object()
        if request.method == 'GET':
            position = WatchProgress.objects.filter(user=request.user, video=video).values_list(
                'position_s', flat=True).first()
            return Response({'position_s': position or 0})
        serializer = WatchProgressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        position = serializer.validated_data['position_s']
        if not math.isfinite(position):
            raise ValidationError({'position_s': 'Must be a number.'})
        position = round(min(position, float(video.duration or 0)), 1)
        WatchProgress.objects.update_or_create(user=request.user, video=video, defaults={'position_s': position})
        return Response({'position_s': position})


class WatchHistoryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """The signed-in user's own watch history (their resume positions)."""

    serializer_class = WatchHistorySerializer
    lookup_field = 'video_id'

    def get_queryset(self):
        user = self.request.user
        return WatchProgress.objects.filter(
            user=user, video__in=visible_videos(user),
        ).select_related('video__uploader').order_by('-updated_at')

    def destroy(self, request, video_id=None):
        try:
            video_id = int(video_id)
        except (TypeError, ValueError):
            raise NotFound() from None
        WatchProgress.objects.filter(user=request.user, video_id=video_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['delete'])
    def clear(self, request):
        WatchProgress.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChannelViewSet(viewsets.GenericViewSet):
    """A user's videos as a channel, and subscriptions to it."""

    serializer_class = UserSerializer

    def get_queryset(self):
        return User.objects.filter(is_active=True).exclude(id__in=visibility.blocked_ids(self.request.user))

    def _summary(self, channel):
        return {
            'user': UserSerializer(channel, context={'request': self.request}).data,
            'videos_count': visible_videos(self.request.user).filter(uploader=channel).count(),
            'subscribers_count': ChannelSubscription.objects.filter(channel=channel).count(),
            'is_subscribed': ChannelSubscription.objects.filter(channel=channel,
                                                                subscriber=self.request.user).exists(),
        }

    def list(self, request):
        """Channels the signed-in user subscribes to."""
        subs = ChannelSubscription.objects.filter(
            subscriber=request.user, channel__in=self.get_queryset(),
        ).select_related('channel').order_by('-created_at')
        page = self.paginate_queryset(subs)
        data = [{'user': UserSerializer(s.channel, context={'request': request}).data,
                 'subscribed_at': s.created_at} for s in page]
        return self.get_paginated_response(data)

    def retrieve(self, request, pk=None):
        return Response(self._summary(self.get_object()))

    @action(detail=True, methods=['post', 'delete'])
    def subscribe(self, request, pk=None):
        channel = self.get_object()
        if channel.id == request.user.id:
            raise ValidationError({'detail': "You can't subscribe to yourself."})
        if request.method == 'DELETE':
            ChannelSubscription.objects.filter(subscriber=request.user, channel=channel).delete()
            return Response(self._summary(channel))
        try:
            with transaction.atomic():
                ChannelSubscription.objects.get_or_create(subscriber=request.user, channel=channel)
        except IntegrityError:
            pass
        return Response(self._summary(channel), status=status.HTTP_201_CREATED)


@require_safe
def stream(request, token, path):
    """
    Serve one processed file of a non-public video through a signed playback link.

    The link only says who it was issued to; access is decided again here, on
    every request, by the same visibility rules as the API.
    """
    claims = read_stream_token(token)
    if claims is None or not ASSET_PATH_RE.match(path):
        raise Http404()
    video_id, user_id = claims
    viewer = get_object_or_404(User, pk=user_id, is_active=True)
    video = visible_videos(viewer).filter(pk=video_id).first()
    if video is None or not video.asset_root or path not in (video.asset_files or []):
        raise Http404()
    try:
        fh = default_storage.open(asset_key(video, path), 'rb')
    except FileNotFoundError:
        raise Http404() from None
    response = FileResponse(fh, content_type=CONTENT_TYPES[PurePosixPath(path).suffix])
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = "default-src 'none'; sandbox"
    response['Cache-Control'] = 'private, no-store'
    response['Referrer-Policy'] = 'no-referrer'
    return response
