from django.urls import path
from .views import (NotificationListView, PreferencesView, PushSubscriptionView, mark_all_read, mark_read,
                    unread_count)

urlpatterns = [
    path('', NotificationListView.as_view(), name='notification-list'),
    path('unread-count/', unread_count, name='notification-unread-count'),
    path('mark-all-read/', mark_all_read, name='notification-mark-all-read'),
    path('<int:pk>/read/', mark_read, name='notification-read'),
    path('preferences/', PreferencesView.as_view(), name='notification-preferences'),
    path('push/', PushSubscriptionView.as_view(), name='notification-push'),
]
