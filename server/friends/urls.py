from django.urls import path
from . import views
from views import FriendsView

urlpatterns = [
    path('', FriendsView, name='friends'),
]
