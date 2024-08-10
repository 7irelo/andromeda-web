from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ChatRoomViewSet, MessageViewSet

router = DefaultRouter()
router.register('rooms', ChatRoomViewSet, basename='chatroom')
router.register('messages', MessageViewSet, basename='message')

urlpatterns = [path('', include(router.urls))]
