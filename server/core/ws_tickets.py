"""
Single-use, short-lived WebSocket tickets.

Browsers can't set headers on a WebSocket handshake, and a JWT in the query
string leaks into proxy and access logs. The client trades its access token for
an opaque ticket over authenticated HTTPS, connects with ``?ticket=...``, and
the ticket is deleted on first use.
"""
import secrets

from django.core.cache import cache

TICKET_TTL_SECONDS = 30
_PREFIX = 'ws-ticket:'


def issue(user_id):
    ticket = secrets.token_urlsafe(32)
    cache.set(_PREFIX + ticket, user_id, TICKET_TTL_SECONDS)
    return ticket


def redeem(ticket):
    if not ticket or len(ticket) > 64:
        return None
    key = _PREFIX + ticket
    user_id = cache.get(key)
    # delete() reports whether this call removed the key, so two concurrent
    # handshakes can't both redeem the same ticket.
    if user_id is not None and cache.delete(key):
        return user_id
    return None
