from django.urls import path
from .views import PageListView, PageDetailView, PageFollowView, PageLikeView

urlpatterns = [
    path('', PageListView.as_view(), name='pages-list'),
    path('<str:uid>/', PageDetailView.as_view(), name='page-detail'),
    path('<str:uid>/follow/', PageFollowView.as_view(), name='page-follow'),
    path('<str:uid>/like/', PageLikeView.as_view(), name='page-like'),
]
