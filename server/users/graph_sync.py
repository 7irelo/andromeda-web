"""
Postgres → Neo4j projection.

Graph writes never run inside a web request. Signals record an outbox event
(``outbox.emit``) on the same connection as the change, so the event commits
or rolls back with it; the outbox drain applies it with idempotent
``MERGE``/``DELETE`` Cypher (``outbox.graph``) and retries with backoff.
Postgres stays the source of truth; Neo4j is a read model for recommendations,
and a nightly reconciliation repairs any drift.
"""
import inspect
import logging

from celery import shared_task

import outbox
from outbox import handlers

logger = logging.getLogger(__name__)

RETRY = dict(autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=300, max_retries=8)


def user_changed(user):
    outbox.emit('graph.sync_user', user_id=user.id, username=user.username, display_name=user.full_name,
                is_verified=bool(user.is_verified))


def user_deleted(user_id):
    outbox.emit('graph.delete_user', user_id=user_id)


def friends_linked(a_id, b_id):
    outbox.emit('graph.link_friends', a_id=a_id, b_id=b_id)


def friends_unlinked(a_id, b_id):
    outbox.emit('graph.unlink_friends', a_id=a_id, b_id=b_id)


def post_created(post_id, author_id):
    outbox.emit('graph.sync_post', post_id=post_id, author_id=author_id)


def post_deleted(post_id):
    outbox.emit('graph.delete_post', post_id=post_id)


def like_added(user_id, post_id):
    outbox.emit('graph.link_like', user_id=user_id, post_id=post_id)


def like_removed(user_id, post_id):
    outbox.emit('graph.unlink_like', user_id=user_id, post_id=post_id)


def enqueue(task, *args):
    """Compatibility shim for callers of the old API: records the equivalent outbox event."""
    names = list(inspect.signature(handlers.HANDLERS[task.name]).parameters)[1:]
    outbox.emit(task.name, **dict(zip(names, args, strict=True)))


# ── Legacy tasks ─────────────────────────────────────────────────────────────
# Kept so messages queued before the outbox existed still drain after a deploy.

def _apply(kind, **payload):
    from outbox.graph import get_graph
    handlers.HANDLERS[kind](get_graph(), **payload)


@shared_task(name='graph.sync_user', **RETRY)
def sync_user(user_id, username, display_name, is_verified):
    _apply('graph.sync_user', user_id=user_id, username=username, display_name=display_name, is_verified=is_verified)


@shared_task(name='graph.delete_user', **RETRY)
def delete_user(user_id):
    _apply('graph.delete_user', user_id=user_id)


@shared_task(name='graph.link_friends', **RETRY)
def link_friends(a_id, b_id):
    _apply('graph.link_friends', a_id=a_id, b_id=b_id)


@shared_task(name='graph.unlink_friends', **RETRY)
def unlink_friends(a_id, b_id):
    _apply('graph.unlink_friends', a_id=a_id, b_id=b_id)


@shared_task(name='graph.sync_post', **RETRY)
def sync_post(post_id, author_id):
    _apply('graph.sync_post', post_id=post_id, author_id=author_id)


@shared_task(name='graph.delete_post', **RETRY)
def delete_post(post_id):
    _apply('graph.delete_post', post_id=post_id)


@shared_task(name='graph.link_like', **RETRY)
def link_like(user_id, post_id):
    _apply('graph.link_like', user_id=user_id, post_id=post_id)


@shared_task(name='graph.unlink_like', **RETRY)
def unlink_like(user_id, post_id):
    _apply('graph.unlink_like', user_id=user_id, post_id=post_id)
