from django.urls import path
from .views import MessagesView, ChatView

urlpatterns = [
    path('', MessagesView.as_view(), name='messages-list'),
    path('<str:pk>/', ChatView.as_view(), name='chat-detail'),
]
