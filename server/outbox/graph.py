"""
The Neo4j projection's write and read operations, in one place.

Every write is idempotent (``MERGE`` / ``DELETE`` of what matches) so the
outbox can re-run an event after a crash or a retry. Edges are only created
between nodes that already exist (``MATCH``): an edge event that arrives
before its nodes, or after one was deleted, is a no-op that reconciliation
repairs, rather than a way to resurrect an erased account's node.

``InMemoryGraph`` implements the same interface for tests.
"""


class Neo4jGraph:
    def run(self, query, params=None):
        from neomodel import db

        rows, _ = db.cypher_query(query, params or {})
        return rows

    # ── Writes (single) ──────────────────────────────────────────────────────

    def upsert_users(self, users):
        """``users``: dicts with user_id, username, display_name, is_verified."""
        if users:
            self.run(
                'UNWIND $rows AS row '
                'MERGE (u:UserNode {user_id: row.user_id}) ON CREATE SET u.uid = randomUUID() '
                'SET u.username = row.username, u.display_name = row.display_name, '
                'u.is_verified = row.is_verified',
                {'rows': list(users)},
            )

    def delete_users(self, user_ids):
        if user_ids:
            self.run('MATCH (u:UserNode) WHERE u.user_id IN $ids DETACH DELETE u', {'ids': list(user_ids)})

    def link_friends(self, pairs):
        if pairs:
            self.run(
                'UNWIND $pairs AS pair '
                'MATCH (a:UserNode {user_id: pair[0]}), (b:UserNode {user_id: pair[1]}) '
                'MERGE (a)-[:FRIEND_WITH]-(b)',
                {'pairs': [list(p) for p in pairs]},
            )

    def unlink_friends(self, pairs):
        if pairs:
            self.run(
                'UNWIND $pairs AS pair '
                'MATCH (a:UserNode {user_id: pair[0]})-[r:FRIEND_WITH]-(b:UserNode {user_id: pair[1]}) DELETE r',
                {'pairs': [list(p) for p in pairs]},
            )

    def upsert_posts(self, posts):
        """``posts``: dicts with post_id, author_id."""
        if posts:
            self.run(
                'UNWIND $rows AS row '
                'MERGE (p:PostNode {post_id: row.post_id}) ON CREATE SET p.uid = randomUUID() '
                'SET p.author_id = row.author_id '
                'WITH p, row MATCH (u:UserNode {user_id: row.author_id}) MERGE (u)-[:CREATED]->(p)',
                {'rows': list(posts)},
            )

    def delete_posts(self, post_ids):
        if post_ids:
            self.run('MATCH (p:PostNode) WHERE p.post_id IN $ids DETACH DELETE p', {'ids': list(post_ids)})

    def link_likes(self, pairs):
        if pairs:
            self.run(
                'UNWIND $pairs AS pair '
                'MATCH (u:UserNode {user_id: pair[0]}), (p:PostNode {post_id: pair[1]}) MERGE (u)-[:LIKED]->(p)',
                {'pairs': [list(p) for p in pairs]},
            )

    def unlink_likes(self, pairs):
        if pairs:
            self.run(
                'UNWIND $pairs AS pair '
                'MATCH (u:UserNode {user_id: pair[0]})-[r:LIKED]->(p:PostNode {post_id: pair[1]}) DELETE r',
                {'pairs': [list(p) for p in pairs]},
            )

    # ── Reads for reconciliation, by id range [lo, hi) ───────────────────────

    def max_ids(self):
        rows = self.run('OPTIONAL MATCH (u:UserNode) WITH max(u.user_id) AS mu '
                        'OPTIONAL MATCH (p:PostNode) RETURN mu, max(p.post_id)')
        mu, mp = rows[0] if rows else (None, None)
        return int(mu or 0), int(mp or 0)

    def user_ids(self, lo, hi):
        rows = self.run('MATCH (u:UserNode) WHERE u.user_id >= $lo AND u.user_id < $hi RETURN u.user_id',
                        {'lo': lo, 'hi': hi})
        return {int(r[0]) for r in rows}

    def friend_pairs(self, lo, hi):
        """Friendships whose lower user id falls in the range, as (low, high) tuples."""
        rows = self.run(
            'MATCH (a:UserNode)-[:FRIEND_WITH]-(b:UserNode) '
            'WHERE a.user_id >= $lo AND a.user_id < $hi AND a.user_id < b.user_id '
            'RETURN DISTINCT a.user_id, b.user_id',
            {'lo': lo, 'hi': hi},
        )
        return {(int(a), int(b)) for a, b in rows}

    def post_ids(self, lo, hi):
        rows = self.run('MATCH (p:PostNode) WHERE p.post_id >= $lo AND p.post_id < $hi RETURN p.post_id',
                        {'lo': lo, 'hi': hi})
        return {int(r[0]) for r in rows}

    def like_pairs(self, lo, hi):
        """Likes on posts in the range, as (user_id, post_id) tuples."""
        rows = self.run(
            'MATCH (u:UserNode)-[:LIKED]->(p:PostNode) WHERE p.post_id >= $lo AND p.post_id < $hi '
            'RETURN DISTINCT u.user_id, p.post_id',
            {'lo': lo, 'hi': hi},
        )
        return {(int(u), int(p)) for u, p in rows}


class InMemoryGraph:
    """Same contract as ``Neo4jGraph``, backed by dicts and sets. For tests."""

    def __init__(self):
        self.users = {}
        self.posts = {}
        self.friends = set()   # frozenset({a, b})
        self.likes = set()     # (user_id, post_id)
        self.calls = 0

    def _tick(self):
        self.calls += 1

    def upsert_users(self, users):
        self._tick()
        for u in users:
            self.users[u['user_id']] = dict(u)

    def delete_users(self, user_ids):
        self._tick()
        for uid in user_ids:
            self.users.pop(uid, None)
            self.friends = {f for f in self.friends if uid not in f}
            self.likes = {lk for lk in self.likes if lk[0] != uid}

    def link_friends(self, pairs):
        self._tick()
        for a, b in pairs:
            if a in self.users and b in self.users:
                self.friends.add(frozenset((a, b)))

    def unlink_friends(self, pairs):
        self._tick()
        for a, b in pairs:
            self.friends.discard(frozenset((a, b)))

    def upsert_posts(self, posts):
        self._tick()
        for p in posts:
            self.posts[p['post_id']] = dict(p)

    def delete_posts(self, post_ids):
        self._tick()
        for pid in post_ids:
            self.posts.pop(pid, None)
            self.likes = {lk for lk in self.likes if lk[1] != pid}

    def link_likes(self, pairs):
        self._tick()
        for uid, pid in pairs:
            if uid in self.users and pid in self.posts:
                self.likes.add((uid, pid))

    def unlink_likes(self, pairs):
        self._tick()
        for pair in pairs:
            self.likes.discard(tuple(pair))

    def max_ids(self):
        return max(self.users, default=0), max(self.posts, default=0)

    def user_ids(self, lo, hi):
        return {u for u in self.users if lo <= u < hi}

    def friend_pairs(self, lo, hi):
        pairs = {tuple(sorted(f)) for f in self.friends}
        return {p for p in pairs if lo <= p[0] < hi}

    def post_ids(self, lo, hi):
        return {p for p in self.posts if lo <= p < hi}

    def like_pairs(self, lo, hi):
        return {lk for lk in self.likes if lo <= lk[1] < hi}


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = Neo4jGraph()
    return _graph
