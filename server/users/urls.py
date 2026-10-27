from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DeleteAccountView, FriendRequestViewSet, LoginView, LogoutAllView, LogoutView, MeView,
    PasswordChangeView, PasswordResetConfirmView, PasswordResetRequestView, RefreshView,
    RegisterView, UserViewSet, WebSocketTicketView,
)

router = DefaultRouter()
router.register('users', UserViewSet, basename='user')
router.register('friend-requests', FriendRequestViewSet, basename='friend-request')

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('token/refresh/', RefreshView.as_view(), name='token-refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('logout-all/', LogoutAllView.as_view(), name='logout-all'),
    path('password/change/', PasswordChangeView.as_view(), name='password-change'),
    path('password/reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path('password/reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('ws-ticket/', WebSocketTicketView.as_view(), name='ws-ticket'),
    path('me/', MeView.as_view(), name='me'),
    path('me/delete/', DeleteAccountView.as_view(), name='me-delete'),
    path('', include(router.urls)),
]
