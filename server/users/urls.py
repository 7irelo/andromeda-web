from django.urls import path
from .views import UserView, FriendsView, UserPostsView

urlpatterns = [
    path('<str:username>/', UserView.as_view(), name='user-detail'),
    path('<str:username>/friends/', FriendsView.as_view(), name='user-friends'),
    path('<str:username>/posts/', UserPostsView.as_view(), name='user-posts'),
]
