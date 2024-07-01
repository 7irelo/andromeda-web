from django.urls import path
from .views import UserView

urlpatterns = [
    path('users/<str:username>/', UserView.as_view(), name='user-detail'),
]
