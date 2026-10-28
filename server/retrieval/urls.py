from django.urls import path

from .views import AskView, SemanticSearchView

urlpatterns = [
    path('search/semantic/', SemanticSearchView.as_view(), name='semantic-search'),
    path('ask/', AskView.as_view(), name='ask'),
]
