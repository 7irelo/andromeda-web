"""
Client for the internal AI service.

Each call carries a fresh HS256 service token (60 s, audience-bound) whose
subject is the acting user. Model and provider keys exist only inside the AI
service; Django never sees them and the browser never talks to it directly.
"""
import json
import time
import uuid

import jwt
import urllib3
from django.conf import settings

_http = urllib3.PoolManager(timeout=urllib3.Timeout(connect=2.0, read=45.0), retries=False)


class AIUnavailable(Exception):
    pass


class AIRejected(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def enabled():
    return bool(settings.AI_SERVICE_URL and settings.AI_SERVICE_SECRET)


def _token(user_id):
    now = int(time.time())
    return jwt.encode(
        {'iss': 'andromeda-api', 'aud': 'andromeda-ai', 'sub': str(user_id),
         'iat': now, 'exp': now + 60, 'jti': uuid.uuid4().hex},
        settings.AI_SERVICE_SECRET, algorithm='HS256',
    )


def call(path, payload, user_id):
    from observability import request_id

    if not enabled():
        raise AIUnavailable('AI service is not configured')
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {_token(user_id)}'}
    rid = request_id.get()
    if rid:
        headers[request_id.HEADER] = rid
    try:
        resp = _http.request(
            'POST', settings.AI_SERVICE_URL.rstrip('/') + path,
            body=json.dumps(payload).encode(),
            headers=headers,
        )
    except urllib3.exceptions.HTTPError as exc:
        raise AIUnavailable(str(exc)) from exc
    if resp.status >= 500:
        raise AIUnavailable(f'AI service returned {resp.status}')
    data = json.loads(resp.data or b'{}')
    if resp.status >= 400:
        raise AIRejected(resp.status, data.get('detail', 'Request rejected'))
    return data
