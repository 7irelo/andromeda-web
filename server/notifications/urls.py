from django.urls import path
from .views import NotificationsView, MarkNotificationAsReadView

urlpatterns = [
    path('', NotificationsView.as_view(), name='notifications-list'),
    path('<int:pk>/read/', MarkNotificationAsReadView.as_view(), name='mark-notification-as-read'),
]
