
"""
Definition of urls for server.
"""

from datetime import datetime
from django.urls import path, include
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from app import forms, views


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('app.urls')),
    path('api/users', include('users.urls')),
    path('api/posts', include('posts.urls')),
    path('api/friends', include('friends.urls')),
    path('api/messages', include('messages.urls')),
    path('api/watch', include('watch.urls')),
    path('api/notifications', include('notifications.urls')),
    path('api/marketplace', include('marketplace.urls')),
    path('api/groups', include('groups.urls')),
    path('api/pages', include('pages.urls')),
]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
