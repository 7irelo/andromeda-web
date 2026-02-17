from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PostViewSet, CommentViewSet

router = DefaultRouter()
router.register('', PostViewSet, basename='post')
router.register('comments', CommentViewSet, basename='comment')

urlpatterns = [path('', include(router.urls))]
