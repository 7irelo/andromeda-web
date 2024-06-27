from django.urls import path
from .views import FriendsView

urlpatterns = [
    path('', FriendsView.as_view(), name='friends'),
]
