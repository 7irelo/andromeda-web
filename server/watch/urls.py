from django.urls import path
from .views import RecommendedVideosView, VideosView, VideoView, VideoCommentView

urlpatterns = [
    path('recommended/', RecommendedVideosView.as_view(), name='recommended-videos'),
    path('', VideosView.as_view(), name='videos'),
    path('<int:pk>/', VideoView.as_view(), name='video-detail'),
    path('<int:video_pk>/comments/<int:pk>/', VideoCommentView.as_view(), name='video-comment-detail'),
    path('<int:video_pk>/comments/', VideoCommentView.as_view(), name='video-comment-create'),
]
