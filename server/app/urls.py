from django.urls import path
from .views import (
    RegisterView, LoginView, UserView, UpdateUserView, LogoutView, HomeView, 
    PostView, CreatePostView, UpdatePostView, DeletePostView, DeleteCommentView
)

urlpatterns = [
    # authentication
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),

    # profile
    path('<str:pk>/', UserView.as_view(), name='profile'),
    path('update-user/', UpdateUserView.as_view(), name='update-user'),

    # posts
    path('post/<str:pk>/', PostView.as_view(), name='post'),
    path('create-post/', CreatePostView.as_view(), name='create-post'),
    path('update-post/<str:pk>/', UpdatePostView.as_view(), name='update-post'),
    path('delete-post/<str:pk>/', DeletePostView.as_view(), name='delete-post'),
    path('delete-comment/<str:pk>/', DeleteCommentView.as_view(), name='delete-comment'),
]
