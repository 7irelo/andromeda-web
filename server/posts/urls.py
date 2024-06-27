from django.urls import path
from .views import (
    PostView, CreatePostView, UpdatePostView, DeletePostView, DeleteCommentView
)

urlpatterns = [
    # Posts
    path('post/<str:pk>/', PostView.as_view(), name='post'),
    path('create-post/', CreatePostView.as_view(), name='create-post'),
    path('update-post/<str:pk>/', UpdatePostView.as_view(), name='update-post'),
    path('delete-post/<str:pk>/', DeletePostView.as_view(), name='delete-post'),
    
    # Comments
    path('delete-comment/<str:pk>/', DeleteCommentView.as_view(), name='delete-comment'),
]
