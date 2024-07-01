from django.urls import path
from .views import PostsView, PostView, CommentView

urlpatterns = [
    path('/', PostsView.as_view(), name='posts-list'),
    path('/<int:pk>/', PostView.as_view(), name='post-detail'),
    path('/<int:post_pk>/comments/', CommentView.as_view(), name='comments-list'),
    path('/<int:post_pk>/comments/<int:pk>/', CommentView.as_view(), name='comment-detail'),
]
