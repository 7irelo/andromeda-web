"""
Outbox event kinds and how each is applied. Handlers must be idempotent:
the drain may run an event more than once (crash before commit, retries).
"""


def _sync_user(graph, user_id, username, display_name, is_verified):
    graph.upsert_users([{'user_id': user_id, 'username': username, 'display_name': display_name,
                         'is_verified': bool(is_verified)}])


def _delete_user(graph, user_id):
    graph.delete_users([user_id])


def _link_friends(graph, a_id, b_id):
    graph.link_friends([(a_id, b_id)])


def _unlink_friends(graph, a_id, b_id):
    graph.unlink_friends([(a_id, b_id)])


def _sync_post(graph, post_id, author_id):
    graph.upsert_posts([{'post_id': post_id, 'author_id': author_id}])


def _delete_post(graph, post_id):
    graph.delete_posts([post_id])


def _link_like(graph, user_id, post_id):
    graph.link_likes([(user_id, post_id)])


def _unlink_like(graph, user_id, post_id):
    graph.unlink_likes([(user_id, post_id)])


# kind -> handler(graph, **payload). Kinds match the old Celery task names.
HANDLERS = {
    'graph.sync_user': _sync_user,
    'graph.delete_user': _delete_user,
    'graph.link_friends': _link_friends,
    'graph.unlink_friends': _unlink_friends,
    'graph.sync_post': _sync_post,
    'graph.delete_post': _delete_post,
    'graph.link_like': _link_like,
    'graph.unlink_like': _unlink_like,
}
