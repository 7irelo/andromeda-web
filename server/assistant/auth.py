"""
Personal access tokens for the MCP endpoint.

Tokens are bearer secrets shown once; only their SHA-256 is stored. They
authenticate the MCP endpoint and nothing else, so a leaked token can never
reach account settings, token management or the regular API.
"""
import datetime as dt

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.throttling import UserRateThrottle

from core.auth import account_block_reason

from .models import TOKEN_PREFIX, PersonalAccessToken

LAST_USED_RESOLUTION = dt.timedelta(minutes=1)


class PersonalAccessTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != b'bearer':
            return None
        if len(parts) != 2:
            raise AuthenticationFailed('Invalid authorization header.')
        try:
            raw = parts[1].decode('ascii')
        except UnicodeDecodeError:
            raise AuthenticationFailed('Invalid token.') from None
        if not raw.startswith(TOKEN_PREFIX) or len(raw) > 100:
            raise AuthenticationFailed('Invalid token.')
        token = PersonalAccessToken.objects.select_related('user').filter(
            token_hash=PersonalAccessToken.hash(raw)).first()
        if token is None or not token.is_active:
            raise AuthenticationFailed('Invalid, expired or revoked token.')
        user = token.user
        if not user.is_active or account_block_reason(user):
            raise AuthenticationFailed('This account cannot use access tokens right now.')
        now = timezone.now()
        if token.last_used_at is None or now - token.last_used_at > LAST_USED_RESOLUTION:
            PersonalAccessToken.objects.filter(pk=token.pk).update(last_used_at=now)
        return user, token

    def authenticate_header(self, request):
        return 'Bearer realm="andromeda-mcp"'


class _ScopedUserThrottle(UserRateThrottle):
    """A per-user throttle whose rate can be configured but has a safe default."""

    default_rate = '60/min'

    def get_rate(self):
        return self.THROTTLE_RATES.get(self.scope) or self.default_rate


class MCPRateThrottle(_ScopedUserThrottle):
    scope = 'mcp'
    default_rate = '120/min'


class AssistantRunThrottle(_ScopedUserThrottle):
    scope = 'assistant'
    default_rate = '60/hour'

    def allow_request(self, request, view):
        if request.method != 'POST':
            return True
        return super().allow_request(request, view)
