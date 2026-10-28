from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CitiesView, ListingViewSet, CategoryViewSet, SellerView

router = DefaultRouter()
router.register('categories', CategoryViewSet, basename='category')
router.register('listings', ListingViewSet, basename='listing')

urlpatterns = [
    path('sellers/<int:pk>/', SellerView.as_view(), name='marketplace-seller'),
    path('cities/', CitiesView.as_view(), name='marketplace-cities'),
    path('', include(router.urls)),
]
