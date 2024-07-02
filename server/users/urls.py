from django.urls import path
from .views import UserView, FriendsView

app_name = 'users'

urlpatterns = [
    path('users/<str:username>/', UserView.as_view(), name='user-detail'),
    path('users/<str:username>/friends/', FriendsView.as_view(), name='user-friends'),
]
