"""
Assistant API: runs, proposals and personal access tokens.

All endpoints use bearer JWT authentication only (no session auth), so they
can't be driven cross-site, and every query is scoped to the requesting user.
"""
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core import ai_client
from core.auth import AndromedaJWTAuthentication

from .auth import AssistantRunThrottle
from .models import AssistantRun, AssistantStep, PersonalAccessToken, Proposal
from .proposals import DecisionError, decide
from .serializers import (ProposalSerializer, RunCreateSerializer, RunSerializer, TokenCreateSerializer,
                          TokenSerializer)

MAX_ACTIVE_RUNS = 3
MAX_ACTIVE_TOKENS = 10


class _AssistantView(APIView):
    authentication_classes = [AndromedaJWTAuthentication]
    permission_classes = [IsAuthenticated]


def _runs(user):
    return AssistantRun.objects.filter(owner=user).prefetch_related(
        Prefetch('steps', queryset=AssistantStep.objects.order_by('index')), 'proposals')


class RunListView(_AssistantView):
    throttle_classes = [*api_settings.DEFAULT_THROTTLE_CLASSES, AssistantRunThrottle]

    def get(self, request):
        return Response(RunSerializer(_runs(request.user)[:20], many=True).data)

    def post(self, request):
        body = RunCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        user = request.user
        if user.ai_opt_out:
            return Response({'detail': 'You have turned off AI features in your settings.'}, status=403)
        if not ai_client.enabled():
            return Response({'detail': 'The assistant is not available right now.'}, status=503)
        if AssistantRun.objects.filter(owner=user, status__in=AssistantRun.ACTIVE).count() >= MAX_ACTIVE_RUNS:
            return Response({'detail': 'Finish or answer your open requests first.'}, status=429)
        follow = body.validated_data.get('follow_up_of')
        previous = AssistantRun.objects.filter(pk=follow, owner=user).first() if follow else None
        if follow and previous is None:
            raise ValidationError({'follow_up_of': 'Not found.'})
        run = AssistantRun.objects.create(owner=user, request_text=body.validated_data['request'],
                                          follow_up_of=previous)
        from .tasks import dispatch
        transaction.on_commit(lambda: dispatch(run.id))
        return Response(RunSerializer(run).data, status=status.HTTP_202_ACCEPTED)


class RunDetailView(_AssistantView):
    def get(self, request, pk):
        run = _runs(request.user).filter(pk=pk).first()
        if run is None:
            return Response({'detail': 'Not found.'}, status=404)
        return Response(RunSerializer(run).data)


class ProposalListView(_AssistantView):
    def get(self, request):
        qs = Proposal.objects.filter(owner=request.user)
        wanted = request.query_params.get('status')
        if wanted:
            qs = qs.filter(status=wanted)
        if wanted == Proposal.STATUS_PENDING:
            qs = qs.filter(expires_at__gt=timezone.now())
        return Response(ProposalSerializer(qs[:50], many=True).data)


class ProposalDecisionView(_AssistantView):
    approve = True

    def post(self, request, pk):
        try:
            proposal = decide(pk, request.user, self.approve)
        except DecisionError as exc:
            return Response({'detail': exc.detail}, status=exc.status)
        return Response(ProposalSerializer(proposal).data)


class ProposalRejectView(ProposalDecisionView):
    approve = False


class TokenListView(_AssistantView):
    throttle_classes = [*api_settings.DEFAULT_THROTTLE_CLASSES, ScopedRateThrottle]
    throttle_scope = 'auth'

    def get(self, request):
        qs = PersonalAccessToken.objects.filter(user=request.user, revoked_at__isnull=True,
                                                expires_at__gt=timezone.now())
        return Response(TokenSerializer(qs, many=True).data)

    def post(self, request):
        body = TokenCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        # A long-lived credential needs the password, not just a 15-minute access token.
        if not request.user.check_password(data['password']):
            raise ValidationError({'password': 'Incorrect password.'})
        active = PersonalAccessToken.objects.filter(user=request.user, revoked_at__isnull=True,
                                                    expires_at__gt=timezone.now()).count()
        if active >= MAX_ACTIVE_TOKENS:
            raise ValidationError({'detail': f'You can have at most {MAX_ACTIVE_TOKENS} active tokens.'})
        token, raw = PersonalAccessToken.issue(request.user, data['name'], data['scopes'], data['expires_in_days'])
        return Response({**TokenSerializer(token).data, 'token': raw}, status=status.HTTP_201_CREATED)


class TokenRevokeView(_AssistantView):
    def delete(self, request, pk):
        updated = PersonalAccessToken.objects.filter(pk=pk, user=request.user, revoked_at__isnull=True).update(
            revoked_at=timezone.now())
        if not updated:
            return Response({'detail': 'Not found.'}, status=404)
        return Response(status=status.HTTP_204_NO_CONTENT)
