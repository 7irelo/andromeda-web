import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from core import visibility, ws_tickets
from core.throttles import AuthRateThrottle
from . import security
from .models import Block, FriendRequest, UserSession
from .serializers import (
    AndromedaTokenSerializer, FriendRequestSerializer, MeSerializer,
    PasswordChangeSerializer, PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer, ReauthSerializer, RegisterSerializer, UserSerializer,
)

User = get_user_model()
logger = logging.getLogger(__name__)


# ── Refresh-token cookie helpers ──────────────────────────────────────────────

def _set_refresh_cookie(response, refresh):
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME, str(refresh),
        max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
        httponly=True, secure=settings.REFRESH_COOKIE_SECURE,
        samesite='Strict', path=settings.REFRESH_COOKIE_PATH,
    )
    return response


def _clear_refresh_cookie(response):
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, path=settings.REFRESH_COOKIE_PATH, samesite='Strict')
    return response


def _session_response(user, request, status_code=status.HTTP_200_OK):
    session = security.start_session(user, request)
    refresh = RefreshToken.for_user(user)
    refresh['sid'] = str(session.pk)  # survives rotation; checked on every refresh
    response = Response({
        'access': str(refresh.access_token),
        'user': MeSerializer(user, context={'request': request}).data,
    }, status=status_code)
    return _set_refresh_cookie(response, refresh)


def _revoke_all_sessions(user):
    security.revoke_sessions(user)
    for token in OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True):
        BlacklistedToken.objects.get_or_create(token=token)


def _refresh_sid(raw):
    if not raw:
        return None
    try:
        return RefreshToken(raw, verify=False).get('sid')
    except TokenError:
        return None


# ── Authentication ────────────────────────────────────────────────────────────

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthRateThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        _send_verification(user)
        return _session_response(user, request, status.HTTP_201_CREATED)


class LoginView(TokenObtainPairView):
    serializer_class = AndromedaTokenSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if security.mfa_enabled(serializer.user):
            # Password alone isn't enough: hand back a short-lived challenge, not a session.
            return Response({'mfa_required': True, 'mfa_token': security.issue_challenge(serializer.user)})
        return _session_response(serializer.user, request)


class LoginMFAView(APIView):
    """Second sign-in step: exchange the challenge plus a TOTP or recovery code for a session."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        token, code = str(request.data.get('mfa_token', '')), str(request.data.get('code', ''))
        invalid = Response({'detail': 'That code is invalid or the sign-in expired. Start again.'},
                           status=status.HTTP_400_BAD_REQUEST)
        redeemed = security.redeem_challenge(token)
        if redeemed is None:
            return invalid
        uid, key = redeemed
        user = User.objects.filter(pk=uid, is_active=True).first()
        device = getattr(user, 'mfa', None) if user else None
        if device is None or not device.enabled or not security.verify_code(device, code):
            return invalid
        security.spend_challenge(key)
        return _session_response(user, request)


class RefreshView(APIView):
    """Rotate the refresh cookie and return a new access token."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if not raw:
            return Response({'detail': 'Not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)
        sid = _refresh_sid(raw)
        if sid is not None and not security.touch_session(sid):
            return _clear_refresh_cookie(
                Response({'detail': 'Session expired.'}, status=status.HTTP_401_UNAUTHORIZED)
            )
        serializer = TokenRefreshSerializer(data={'refresh': raw})
        try:
            serializer.is_valid(raise_exception=True)
        except (TokenError, ValidationError, Exception):
            return _clear_refresh_cookie(
                Response({'detail': 'Session expired.'}, status=status.HTTP_401_UNAUTHORIZED)
            )
        response = Response({'access': serializer.validated_data['access']})
        if 'refresh' in serializer.validated_data:
            _set_refresh_cookie(response, serializer.validated_data['refresh'])
        return response


class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if raw:
            try:
                token = RefreshToken(raw)
                if token.get('sid'):
                    UserSession.objects.filter(pk=token['sid'], user_id=token.get('user_id'),
                                               revoked_at__isnull=True).update(revoked_at=timezone.now())
                token.blacklist()
            except (TokenError, ValueError, DjangoValidationError):
                pass
        return _clear_refresh_cookie(Response(status=status.HTTP_204_NO_CONTENT))


class LogoutAllView(APIView):
    """Revoke every refresh token for this account (all devices)."""

    def post(self, request):
        _revoke_all_sessions(request.user)
        return _clear_refresh_cookie(Response(status=status.HTTP_204_NO_CONTENT))


class PasswordChangeView(APIView):
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save(update_fields=['password'])
        _revoke_all_sessions(user)
        # Keep this device signed in with a fresh session.
        return _session_response(user, request)


class PasswordResetRequestView(APIView):
    """Always answers 202 so the endpoint can't be used to discover accounts."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=serializer.validated_data['email'], is_active=True).first()
        if user:
            try:
                from .tasks import send_password_reset_email
                send_password_reset_email.delay(user.id)
            except Exception:
                logger.warning('Background dispatch failed', exc_info=True)
        return Response({'detail': 'If that email is registered, a reset link is on its way.'},
                        status=status.HTTP_202_ACCEPTED)


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(data['uid'])), is_active=True)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            user = None
        if user is None or not default_token_generator.check_token(user, data['token']):
            raise ValidationError({'detail': 'This reset link is invalid or has expired.'})
        try:
            validate_password(data['new_password'], user)
        except DjangoValidationError as exc:
            raise ValidationError({'new_password': list(exc.messages)})
        user.set_password(data['new_password'])
        user.save(update_fields=['password'])
        _revoke_all_sessions(user)
        return Response({'detail': 'Password updated. Please sign in.'})


class WebSocketTicketView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'ws_ticket'

    def post(self, request):
        return Response({'ticket': ws_tickets.issue(request.user.id), 'expires_in': ws_tickets.TICKET_TTL_SECONDS})


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = MeSerializer

    def get_object(self):
        return self.request.user

    def perform_update(self, serializer):
        was_opted_out = self.request.user.ai_opt_out
        user = serializer.save()
        if user.ai_opt_out != was_opted_out:
            from retrieval.tasks import apply_ai_opt_out
            transaction.on_commit(lambda: apply_ai_opt_out.delay(user.id))


class DeleteAccountView(APIView):
    """Account deletion requires re-entering the password."""

    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        ReauthSerializer(data=request.data, context={'request': request}).is_valid(raise_exception=True)
        user = request.user
        _revoke_all_sessions(user)
        user.delete()
        return _clear_refresh_cookie(Response(status=status.HTTP_204_NO_CONTENT))


# ── Devices, two-factor and email verification ────────────────────────────────

def _send_verification(user):
    def dispatch():
        try:
            from .tasks import send_verification_email
            send_verification_email.delay(user.id)
        except Exception:
            logger.warning('Background dispatch failed', exc_info=True)
    transaction.on_commit(dispatch)


class SessionListView(APIView):
    """The devices signed in to this account."""

    def get(self, request):
        current = _refresh_sid(request.COOKIES.get(settings.REFRESH_COOKIE_NAME))
        rows = UserSession.objects.filter(user=request.user, revoked_at__isnull=True)[:50]
        return Response([{
            'id': str(s.pk), 'user_agent': s.user_agent, 'network': s.ip_prefix,
            'created_at': s.created_at, 'last_seen_at': s.last_seen_at, 'current': str(s.pk) == current,
        } for s in rows])


class SessionRevokeView(APIView):
    def delete(self, request, session_id):
        updated = UserSession.objects.filter(
            pk=session_id, user=request.user, revoked_at__isnull=True).update(revoked_at=timezone.now())
        if not updated:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MFAStatusView(APIView):
    def get(self, request):
        device = getattr(request.user, 'mfa', None)
        on = bool(device and device.enabled)
        return Response({'enabled': on, 'recovery_codes_left': len(device.recovery_codes) if on else 0})


class MFASetupView(APIView):
    """Start (or restart) TOTP setup. Requires the password; refused while 2FA is on."""

    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        ReauthSerializer(data=request.data, context={'request': request}).is_valid(raise_exception=True)
        if security.mfa_enabled(request.user):
            raise ValidationError({'detail': 'Two-factor sign-in is already on. Turn it off first.'})
        secret, uri = security.begin_setup(request.user)
        return Response({'secret': secret, 'otpauth_uri': uri, 'qr_png': security.qr_data_uri(uri)})


class MFAEnableView(APIView):
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        device = getattr(request.user, 'mfa', None)
        codes = security.enable(device, str(request.data.get('code', ''))) if device else None
        if codes is None:
            raise ValidationError({'code': 'That code is not valid. Check your authenticator app and try again.'})
        # Devices that signed in with only a password are signed out.
        security.revoke_sessions(request.user, exclude=_refresh_sid(request.COOKIES.get(settings.REFRESH_COOKIE_NAME)))
        return Response({'enabled': True, 'recovery_codes': codes})


class MFADisableView(APIView):
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        ReauthSerializer(data=request.data, context={'request': request}).is_valid(raise_exception=True)
        device = getattr(request.user, 'mfa', None)
        if not device or not device.enabled:
            return Response({'enabled': False})
        if not security.verify_code(device, str(request.data.get('code', ''))):
            raise ValidationError({'code': 'That code is not valid.'})
        device.delete()
        return Response({'enabled': False})


class EmailVerifyView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        user = security.verify_email_token(str(request.data.get('token', '')))
        if user is None:
            raise ValidationError({'detail': 'This verification link is invalid or has expired.'})
        if not user.email_verified:
            user.email_verified = True
            user.save(update_fields=['email_verified'])
        return Response({'detail': 'Email address verified.'})


class EmailResendView(APIView):
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        if not request.user.email_verified:
            _send_verification(request.user)
        return Response({'detail': 'If your email still needs verifying, a new link is on its way.'},
                        status=status.HTTP_202_ACCEPTED)


# ── Users, friends and blocking ───────────────────────────────────────────────

class UserViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UserSerializer

    def get_queryset(self):
        qs = User.objects.filter(is_active=True).exclude(id__in=visibility.blocked_ids(self.request.user))
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(searchable=True).filter(
                Q(username__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )
        elif self.action == 'list':
            # No unfiltered directory of every account.
            qs = qs.none()
        return qs

    def _lookup(self, qs):
        """Detail routes accept a numeric id or a username."""
        lookup = str(self.kwargs.get('pk', ''))
        return get_object_or_404(qs, **({'pk': lookup} if lookup.isdigit() else {'username': lookup}))

    def _detail_object(self):
        # Blocked users (either direction) resolve to 404, like non-existent ones.
        return self._lookup(
            User.objects.filter(is_active=True).exclude(id__in=visibility.blocked_ids(self.request.user))
        )

    def retrieve(self, request, *args, **kwargs):
        return Response(self.get_serializer(self._detail_object()).data)

    @action(detail=True, methods=['get'])
    def friends(self, request, pk=None):
        target = self._detail_object()
        if not visibility.can_view_friends_list(request.user, target):
            raise PermissionDenied('This friends list is private.')
        ids = visibility.friend_ids(target) - visibility.blocked_ids(request.user)
        page = self.paginate_queryset(User.objects.filter(id__in=ids, is_active=True).order_by('first_name'))
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @action(detail=True, methods=['post', 'delete'])
    def block(self, request, pk=None):
        if request.method == 'DELETE':
            target = self._lookup(User.objects.filter(blocked_by_set__blocker=request.user))
        else:
            target = self._detail_object()
        if target.id == request.user.id:
            raise ValidationError({'detail': 'You cannot block yourself.'})
        if request.method == 'DELETE':
            Block.objects.filter(blocker=request.user, blocked=target).delete()
            return Response({'blocked': False})
        with transaction.atomic():
            Block.objects.get_or_create(blocker=request.user, blocked=target)
            # Blocking severs the relationship and any pending requests.
            FriendRequest.objects.filter(
                Q(sender=request.user, receiver=target) | Q(sender=target, receiver=request.user)
            ).delete()  # counters and the graph update via signals
        return Response({'blocked': True})

    @action(detail=False, methods=['get'])
    def blocked(self, request):
        users = User.objects.filter(blocked_by_set__blocker=request.user)
        return Response(UserSerializer(users, many=True, context={'request': request}).data)

    @action(detail=True, methods=['delete'])
    def friend(self, request, pk=None):
        """Unfriend."""
        target = self._detail_object()
        deleted, _ = FriendRequest.objects.filter(
            Q(sender=request.user, receiver=target) | Q(sender=target, receiver=request.user),
            status=FriendRequest.STATUS_ACCEPTED,
        ).delete()
        if not deleted:
            raise ValidationError({'detail': 'You are not friends with this user.'})
        return Response({'is_friend': False})

    @action(detail=False, methods=['get'])
    def suggestions(self, request):
        """Friend suggestions via the Neo4j graph, with a relational fallback."""
        exclude = visibility.blocked_ids(request.user) | visibility.friend_ids(request.user) | {request.user.id}
        involved = FriendRequest.objects.filter(Q(sender=request.user) | Q(receiver=request.user))
        exclude |= set(involved.values_list('sender_id', flat=True))
        exclude |= set(involved.values_list('receiver_id', flat=True))
        base = User.objects.filter(is_active=True, searchable=True).exclude(id__in=exclude)
        try:
            if not settings.NEO4J_ENABLED:
                raise LookupError
            from users.graph_models import UserNode
            node = UserNode.nodes.get_or_none(user_id=request.user.id)
            if node:
                ids = [r['user_id'] for r in node.get_friend_recommendations()]
                users = base.filter(id__in=ids)
                if users.exists():
                    return Response(UserSerializer(users, many=True, context={'request': request}).data)
        except Exception:
            logger.warning('Background dispatch failed', exc_info=True)
        users = base.order_by('-created_at')[:10]
        return Response(UserSerializer(users, many=True, context={'request': request}).data)


class FriendRequestViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                           mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = FriendRequestSerializer

    def get_queryset(self):
        return FriendRequest.objects.filter(
            Q(sender=self.request.user) | Q(receiver=self.request.user)
        ).select_related('sender', 'receiver')

    def perform_create(self, serializer):
        receiver = get_object_or_404(User, id=self.request.data.get('receiver_id'), is_active=True)
        if not visibility.can_send_friend_request(self.request.user, receiver):
            raise PermissionDenied('This user is not accepting friend requests from you.')
        if FriendRequest.objects.filter(sender=receiver, receiver=self.request.user).exists():
            raise ValidationError({'detail': 'This user already sent you a request.'})
        try:
            fr = serializer.save(sender=self.request.user, receiver=receiver)
        except IntegrityError:
            raise ValidationError({'detail': 'Friend request already sent.'})
        try:
            from notifications.tasks import send_friend_request_notification
            send_friend_request_notification.delay(self.request.user.id, receiver.id, fr.id)
        except Exception:
            logger.warning('Background dispatch failed', exc_info=True)

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        fr = get_object_or_404(FriendRequest, pk=pk, receiver=request.user, status=FriendRequest.STATUS_PENDING)
        fr.status = FriendRequest.STATUS_ACCEPTED
        fr.save()
        return Response({'status': 'accepted'})

    @action(detail=True, methods=['post'])
    def decline(self, request, pk=None):
        fr = get_object_or_404(FriendRequest, pk=pk, receiver=request.user, status=FriendRequest.STATUS_PENDING)
        # Delete rather than keep a 'declined' row so the sender may try again later.
        fr.delete()
        return Response({'status': 'declined'})

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        fr = get_object_or_404(FriendRequest, pk=pk, sender=request.user, status=FriendRequest.STATUS_PENDING)
        fr.delete()
        return Response({'status': 'cancelled'})

    @action(detail=False, methods=['get'])
    def received(self, request):
        qs = self.get_queryset().filter(receiver=request.user, status=FriendRequest.STATUS_PENDING)
        return Response(self.get_serializer(qs, many=True).data)

    @action(detail=False, methods=['get'])
    def sent(self, request):
        qs = self.get_queryset().filter(sender=request.user, status=FriendRequest.STATUS_PENDING)
        return Response(self.get_serializer(qs, many=True).data)
