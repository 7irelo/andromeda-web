from django.urls import re_path

from .voice import VoiceConsumer

websocket_urlpatterns = [
    re_path(r'ws/voice/$', VoiceConsumer.as_asgi()),
]
