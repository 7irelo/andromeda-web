from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ListingViewSet, CategoryViewSet

router = DefaultRouter()
router.register('categories', CategoryViewSet, basename='category')
router.register('listings', ListingViewSet, basename='listing')

urlpatterns = [path('', include(router.urls))]
