from django.urls import path
from .views import MarketplaceView, ItemView

urlpatterns = [
    path('', MarketplaceView.as_view(), name='marketplace'),  # Register MarketplaceView
    path('item/<str:pk>/', ItemView.as_view(), name='item'),    # Register ItemView with dynamic item ID
]
