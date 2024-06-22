from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenBlacklistView
from .views import (
    RegisterView, LoginView, MeView,
    UserViewSet, FriendRequestViewSet,
)

router = DefaultRouter()
router.register('users', UserViewSet, basename='user')
router.register('friend-requests', FriendRequestViewSet, basename='friend-request')

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('token/blacklist/', TokenBlacklistView.as_view(), name='token-blacklist'),
    path('me/', MeView.as_view(), name='me'),
    path('', include(router.urls)),
]
