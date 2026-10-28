from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import GroupInviteView, GroupViewSet

router = DefaultRouter()
router.register('', GroupViewSet, basename='group')

urlpatterns = [
    # Before the router so "invites" is never read as a group id.
    path('invites/<str:token>/', GroupInviteView.as_view(), name='group-invite-redeem'),
    path('', include(router.urls)),
]
