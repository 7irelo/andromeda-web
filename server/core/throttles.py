from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class WriteRateThrottle(UserRateThrottle):
    """Caps state-changing requests per user. Reads fall under the 'user' rate."""

    scope = 'write'

    def allow_request(self, request, view):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True
        return super().allow_request(request, view)


class AuthRateThrottle(AnonRateThrottle):
    """Per-IP brute-force protection for login, register, refresh and password reset."""

    scope = 'auth'
