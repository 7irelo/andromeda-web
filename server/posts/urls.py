from django.urls import path
from .views import PostsView, PostView, CreatePostView, UpdatePostView, DeletePostView, CommentView

urlpatterns = [
    path('posts/', PostsView.as_view(), name='posts-list'),
    path('posts/create/', CreatePostView.as_view(), name='create-post'),
    path('posts/<int:pk>/', PostView.as_view(), name='post-detail'),
    path('posts/<int:pk>/update/', UpdatePostView.as_view(), name='update-post'),
    path('posts/<int:pk>/delete/', DeletePostView.as_view(), name='delete-post'),
    path('posts/<int:post_pk>/comments/<int:pk>/', CommentView.as_view(), name='comment-detail'),
    path('posts/<int:post_pk>/comments/', CommentView.as_view(), name='create-comment'),
]
