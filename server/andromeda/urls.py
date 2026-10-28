from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from assistant.mcp import MCPView
from core.search import SearchView


def health_check(request):
    return JsonResponse({'status': 'ok', 'service': 'andromeda-api'})


urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),

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
    path('api/search/', SearchView.as_view(), name='search'),
    path('api/', include('retrieval.urls')),
    path('api/moderation/', include('moderation.urls')),
    path('api/assistant/', include('assistant.urls')),
    path('api/mcp/', MCPView.as_view(), name='mcp'),

    # OpenAPI schema + docs (admin-only outside DEBUG, see SPECTACULAR_SETTINGS)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='api-docs'),

    # Prometheus metrics endpoint. Not exposed publicly: nginx only proxies /api
    # and /ws, and the compose file binds Django's port to localhost.
    path('', include('django_prometheus.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
