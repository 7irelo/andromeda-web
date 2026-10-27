"""
Postgres → Neo4j projection.

Graph writes never run inside a web request. Signals enqueue these tasks with
``transaction.on_commit`` so the graph only sees committed data, and every task
uses idempotent ``MERGE``/``DELETE`` Cypher so Celery retries are safe.
Postgres stays the source of truth; Neo4j is a read model for recommendations.
"""
import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)

RETRY = dict(autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=300, max_retries=8)


def enqueue(task, *args):
    if not getattr(settings, 'NEO4J_ENABLED', True):
        return
    transaction.on_commit(lambda: task.apply_async(args=args, queue='default'))


def _cypher(query, params):
    from neomodel import db
    db.cypher_query(query, params)


@shared_task(name='graph.sync_user', **RETRY)
def sync_user(user_id, username, display_name, is_verified):
    _cypher(
        'MERGE (u:UserNode {user_id: $id}) '
        'ON CREATE SET u.uid = randomUUID() '
        'SET u.username = $username, u.display_name = $name, u.is_verified = $verified',
        {'id': user_id, 'username': username, 'name': display_name, 'verified': is_verified},
    )


@shared_task(name='graph.delete_user', **RETRY)
def delete_user(user_id):
    _cypher('MATCH (u:UserNode {user_id: $id}) DETACH DELETE u', {'id': user_id})


@shared_task(name='graph.link_friends', **RETRY)
def link_friends(a_id, b_id):
    _cypher(
        'MATCH (a:UserNode {user_id: $a}), (b:UserNode {user_id: $b}) MERGE (a)-[:FRIEND_WITH]-(b)',
        {'a': a_id, 'b': b_id},
    )


@shared_task(name='graph.unlink_friends', **RETRY)
def unlink_friends(a_id, b_id):
    _cypher(
        'MATCH (a:UserNode {user_id: $a})-[r:FRIEND_WITH]-(b:UserNode {user_id: $b}) DELETE r',
        {'a': a_id, 'b': b_id},
    )


@shared_task(name='graph.sync_post', **RETRY)
def sync_post(post_id, author_id):
    _cypher(
        'MERGE (p:PostNode {post_id: $pid}) ON CREATE SET p.uid = randomUUID() SET p.author_id = $aid '
        'WITH p MATCH (u:UserNode {user_id: $aid}) MERGE (u)-[:CREATED]->(p)',
        {'pid': post_id, 'aid': author_id},
    )


@shared_task(name='graph.delete_post', **RETRY)
def delete_post(post_id):
    _cypher('MATCH (p:PostNode {post_id: $pid}) DETACH DELETE p', {'pid': post_id})


@shared_task(name='graph.link_like', **RETRY)
def link_like(user_id, post_id):
    _cypher(
        'MATCH (u:UserNode {user_id: $uid}), (p:PostNode {post_id: $pid}) MERGE (u)-[:LIKED]->(p)',
        {'uid': user_id, 'pid': post_id},
    )


@shared_task(name='graph.unlink_like', **RETRY)
def unlink_like(user_id, post_id):
    _cypher(
        'MATCH (u:UserNode {user_id: $uid})-[r:LIKED]->(p:PostNode {post_id: $pid}) DELETE r',
        {'uid': user_id, 'pid': post_id},
    )
