from django.urls import path
from . import views
from views import MarketplaceView, ItemView

urlpatterns = [
    path('', MarketplaceView.as_view(), name='marketplace'),
    path("item/<str:pk>/", ItemView.as_view(), name="item"),
]
