from django.urls import path

from .views import (ProposalDecisionView, ProposalListView, ProposalRejectView, RunDetailView, RunListView,
                    TokenListView, TokenRevokeView)

urlpatterns = [
    path('runs/', RunListView.as_view(), name='assistant-runs'),
    path('runs/<int:pk>/', RunDetailView.as_view(), name='assistant-run'),
    path('proposals/', ProposalListView.as_view(), name='assistant-proposals'),
    path('proposals/<int:pk>/approve/', ProposalDecisionView.as_view(), name='assistant-proposal-approve'),
    path('proposals/<int:pk>/reject/', ProposalRejectView.as_view(), name='assistant-proposal-reject'),
    path('tokens/', TokenListView.as_view(), name='assistant-tokens'),
    path('tokens/<int:pk>/', TokenRevokeView.as_view(), name='assistant-token'),
]
