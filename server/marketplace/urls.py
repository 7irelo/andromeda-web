from django.urls import path
from . import views
from views import MarketplaceView, ItemView

urlpatterns = [
    path('', MarketplaceView, name='marketplace'),
    path("item/<str:pk>/", ItemView, name="item"),
]
