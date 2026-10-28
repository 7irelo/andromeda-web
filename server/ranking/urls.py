from django.urls import path

from .views import FeedEventsView, MyImpressionsView, RankingMetricsView

urlpatterns = [
    path('events/', FeedEventsView.as_view(), name='ranking-events'),
    path('me/impressions/', MyImpressionsView.as_view(), name='ranking-my-impressions'),
    path('metrics/', RankingMetricsView.as_view(), name='ranking-metrics'),
]
