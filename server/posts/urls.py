from django.urls import path
from .views import PostsView, PostView, CommentView, RecommendedPostsView

urlpatterns = [
    path('', PostsView.as_view(), name='posts-list'),
    path('recommended/', RecommendedPostsView.as_view(), name='recommended-posts'),
    path('<int:pk>/', PostView.as_view(), name='post-detail'),
    path('<int:post_pk>/comments/', CommentView.as_view(), name='comments-list'),
    path('<int:post_pk>/comments/<int:pk>/', CommentView.as_view(), name='comment-detail'),
]
