"""
JWT Auth middleware for Django Channels WebSocket connections.
Reads token from query string: ws://host/ws/chat/?token=<JWT>
"""
from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError


@database_sync_to_async
def get_user_from_token(token_str):
    try:
        token = AccessToken(token_str)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        return User.objects.get(id=token['user_id'])
    except (TokenError, Exception):
        return AnonymousUser()


class JWTAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        query_string = scope.get('query_string', b'').decode()
        params = parse_qs(query_string)
        token_list = params.get('token', [])
        if token_list:
            scope['user'] = await get_user_from_token(token_list[0])
        else:
            scope['user'] = AnonymousUser()
        return await self.inner(scope, receive, send)
