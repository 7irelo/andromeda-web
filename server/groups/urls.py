from django.urls import path
from .views import GroupView, GroupMessageView

urlpatterns = [
    path('', GroupView.as_view(), name='group-list-create'),
    path('<str:pk>/', GroupView.as_view(), name='group-detail'),
    path('<str:pk>/messages/', GroupMessageView.as_view(), name='group-messages'),
]
