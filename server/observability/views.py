"""
Same-origin relay for browser error reports (Sentry "tunnel").

The CSP allows ``connect-src 'self'`` only, and ad blockers drop requests to
Sentry's hosts, so the frontend posts envelopes here. Only envelopes for the
configured frontend DSN are relayed, and only to that DSN's own host: the
destination comes from settings, never from the request, so this can't be
used to reach anything else.
"""
import json
import logging
from urllib.parse import urlsplit

import urllib3
from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

MAX_ENVELOPE_BYTES = 256 * 1024
_http = urllib3.PoolManager(timeout=urllib3.Timeout(connect=2.0, read=5.0), retries=False)


class TunnelThrottle(AnonRateThrottle):
    scope = 'anon'


def _target(dsn):
    parts = urlsplit(dsn)
    project = parts.path.strip('/')
    if parts.scheme != 'https' or not parts.hostname or not project.isdigit():
        return None
    return f'https://{parts.hostname}/api/{project}/envelope/'


class ErrorTunnelView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [TunnelThrottle]

    def post(self, request):
        dsn = getattr(settings, 'SENTRY_FRONTEND_DSN', '')
        target = _target(dsn) if dsn else None
        if target is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        body = request.body
        if len(body) > MAX_ENVELOPE_BYTES:
            return Response(status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        try:
            header = json.loads(body.split(b'\n', 1)[0] or b'{}')
        except ValueError:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(header, dict) or header.get('dsn') != dsn:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        try:
            _http.request('POST', target, body=body, headers={'Content-Type': 'application/x-sentry-envelope'})
        except urllib3.exceptions.HTTPError:
            logger.info('Error report relay failed')
        return Response(status=status.HTTP_204_NO_CONTENT)
