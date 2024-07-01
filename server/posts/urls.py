from django.urls import path
from .views import PostsView, PostView, CreatePostView, UpdatePostView, DeletePostView, CommentView

urlpatterns = [
    path('/', PostsView.as_view(), name='posts-list'),
    path('create/', CreatePostView.as_view(), name='create-post'),
    path('<int:pk>/', PostView.as_view(), name='post-detail'),
    path('<int:pk>/update/', UpdatePostView.as_view(), name='update-post'),
    path('<int:pk>/delete/', DeletePostView.as_view(), name='delete-post'),
    path('<int:post_pk>/comments/<int:pk>/', CommentView.as_view(), name='comment-detail'),
    path('<int:post_pk>/comments/create-comment', CommentView.as_view(), name='create-comment'),
]
