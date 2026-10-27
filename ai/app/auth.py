"""
Service-to-service authentication.

Django mints an HS256 token per request (60 s lifetime, audience-bound) whose
subject is the acting user's id. The AI service never trusts a user id from a
request body: identity comes only from this token.
"""
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings

MAX_TOKEN_AGE_SECONDS = 120
_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class ActingUser:
    id: int
    request_id: str


def verify_token(token: str, settings: Settings) -> ActingUser:
    try:
        claims = jwt.decode(
            token,
            settings.ai_service_secret.get_secret_value(),
            algorithms=['HS256'],
            audience=settings.token_audience,
            issuer=settings.token_issuer,
            options={'require': ['exp', 'iat', 'sub', 'aud', 'iss', 'jti']},
            leeway=5,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'Invalid service token') from exc
    if claims['exp'] - claims['iat'] > MAX_TOKEN_AGE_SECONDS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'Service token lifetime too long')
    sub = str(claims['sub'])
    if not sub.isdigit():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'Invalid subject')
    return ActingUser(id=int(sub), request_id=str(claims['jti']))


def acting_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> ActingUser:
    if creds is None or creds.scheme.lower() != 'bearer':
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'Missing service token')
    return verify_token(creds.credentials, settings)
