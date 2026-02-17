from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse


def health_check(request):
    return JsonResponse({'status': 'ok', 'service': 'andromeda-api'})


urlpatterns = [
    path('admin/', admin.site.urls),

    # Health
    path('api/health/', health_check),

    # Auth (JWT)
    path('api/auth/', include('users.urls')),

    # Features
    path('api/posts/', include('posts.urls')),
    path('api/chats/', include('chats.urls')),
    path('api/notifications/', include('notifications.urls')),
    path('api/groups/', include('groups.urls')),
    path('api/marketplace/', include('marketplace.urls')),
    path('api/watch/', include('watch.urls')),
    path('api/pages/', include('pages.urls')),

    # Prometheus metrics endpoint
    path('', include('django_prometheus.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
