from django.urls import path
from .views import PostsView, PostView, CommentView, RecommendedPostsView

urlpatterns = [
    path('', PostsView.as_view(), name='posts-list'),
    path('recommended/', RecommendedPostsView.as_view(), name='recommended-posts'),
    path('<str:uid>/', PostView.as_view(), name='post-detail'),
    path('<str:post_uid>/comments/', CommentView.as_view(), name='comments-list'),
    path('<str:post_uid>/comments/<str:uid>/', CommentView.as_view(), name='comment-detail'),
]
