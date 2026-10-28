from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DeleteAccountView, EmailResendView, EmailVerifyView, FriendRequestViewSet, LoginMFAView, LoginView,
    LogoutAllView, LogoutView, MeView, MFADisableView, MFAEnableView, MFASetupView, MFAStatusView,
    PasswordChangeView, PasswordResetConfirmView, PasswordResetRequestView, RefreshView, RegisterView,
    SessionListView, SessionRevokeView, UserViewSet, WebSocketTicketView, DataExportView, DataExportDownloadView,
    ConsentListView,
)

router = DefaultRouter()
router.register('users', UserViewSet, basename='user')
router.register('friend-requests', FriendRequestViewSet, basename='friend-request')

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('login/mfa/', LoginMFAView.as_view(), name='login-mfa'),
    path('sessions/', SessionListView.as_view(), name='sessions'),
    path('sessions/<uuid:session_id>/', SessionRevokeView.as_view(), name='session-revoke'),
    path('mfa/', MFAStatusView.as_view(), name='mfa-status'),
    path('mfa/setup/', MFASetupView.as_view(), name='mfa-setup'),
    path('mfa/enable/', MFAEnableView.as_view(), name='mfa-enable'),
    path('mfa/disable/', MFADisableView.as_view(), name='mfa-disable'),
    path('email/verify/', EmailVerifyView.as_view(), name='email-verify'),
    path('email/resend/', EmailResendView.as_view(), name='email-resend'),
    path('token/refresh/', RefreshView.as_view(), name='token-refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('logout-all/', LogoutAllView.as_view(), name='logout-all'),
    path('password/change/', PasswordChangeView.as_view(), name='password-change'),
    path('password/reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path('password/reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('ws-ticket/', WebSocketTicketView.as_view(), name='ws-ticket'),
    path('me/', MeView.as_view(), name='me'),
    path('me/delete/', DeleteAccountView.as_view(), name='me-delete'),
    path('me/exports/', DataExportView.as_view(), name='me-exports'),
    path('me/exports/<int:export_id>/download/', DataExportDownloadView.as_view(), name='me-export-download'),
    path('me/consents/', ConsentListView.as_view(), name='me-consents'),
    path('', include(router.urls)),
]
