from django.urls import path
from .views import PostsView, PostView, CommentView

urlpatterns = [
    path('', PostsView.as_view(), name='posts-list'),  # List and create posts
    path('<int:pk>/', PostView.as_view(), name='post-detail'),  # Retrieve, update, and delete a specific post
    path('<int:post_pk>/comments/', CommentView.as_view(), name='comments-list'),  # List and create comments on a specific post
    path('<int:post_pk>/comments/<int:pk>/', CommentView.as_view(), name='comment-detail'),  # Retrieve, update, and delete a specific comment
]
