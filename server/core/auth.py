"""
Request authentication that also enforces account state.

SimpleJWT already rejects inactive (banned) accounts. This adds suspensions
and accounts waiting to be deleted, so an access token issued before the
moderator acted stops working on the next request rather than at expiry.
"""
from django.utils import timezone
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


def account_block_reason(user):
    if user.deletion_scheduled_at is not None:
        return 'This account is scheduled for deletion.'
    if user.suspended_until is not None and user.suspended_until > timezone.now():
        return f'This account is suspended until {user.suspended_until:%d %b %Y}.'
    return None


class AndromedaJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        reason = account_block_reason(user)
        if reason:
            raise AuthenticationFailed(reason, code='account_restricted')
        return user
