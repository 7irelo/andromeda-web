from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AppealView, ModerationCaseViewSet, MyCasesView, ReportView

router = DefaultRouter()
router.register('cases', ModerationCaseViewSet, basename='moderation-case')

urlpatterns = [
    path('reports/', ReportView.as_view(), name='moderation-report'),
    path('mine/', MyCasesView.as_view(), name='moderation-mine'),
    path('mine/<int:case_id>/appeal/', AppealView.as_view(), name='moderation-appeal'),
    path('', include(router.urls)),
]
