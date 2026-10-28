from django.urls import path, include, re_path
from rest_framework.routers import DefaultRouter
from .views import ChannelViewSet, VideoViewSet, WatchHistoryViewSet, stream

router = DefaultRouter()
router.register('videos', VideoViewSet, basename='video')
router.register('history', WatchHistoryViewSet, basename='watch-history')
router.register('channels', ChannelViewSet, basename='channel')

urlpatterns = [
    path('', include(router.urls)),
    # Signed playback links: /api/watch/stream/<token>/master.m3u8 and the
    # relative rendition, segment and image paths it leads to.
    re_path(r'^stream/(?P<token>[A-Za-z0-9_\-:]{16,256})/(?P<path>[A-Za-z0-9_./]{1,64})$', stream,
            name='watch-stream'),
]
