"""
WebSocket authentication for Django Channels.

Clients connect with ``?ticket=<one-time ticket>`` obtained from
``POST /api/auth/ws-ticket/``. JWTs are deliberately not accepted in the URL,
because query strings end up in proxy and access logs.
"""
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

from core import ws_tickets


@database_sync_to_async
def get_user_from_ticket(ticket):
    from django.contrib.auth import get_user_model

    user_id = ws_tickets.redeem(ticket)
    if user_id is None:
        return AnonymousUser()
    return get_user_model().objects.filter(id=user_id, is_active=True).first() or AnonymousUser()


class TicketAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        params = parse_qs(scope.get('query_string', b'').decode())
        ticket = (params.get('ticket') or [None])[0]
        scope = dict(scope, user=await get_user_from_ticket(ticket) if ticket else AnonymousUser())
        return await self.inner(scope, receive, send)
