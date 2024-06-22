"""
Neo4j graph models for Andromeda's social graph.
These mirror the relational User model and power
friend recommendations, feed ranking, and graph queries.
"""
from neomodel import (
    StructuredNode, StringProperty, IntegerProperty,
    BooleanProperty, DateTimeProperty, UniqueIdProperty,
    RelationshipTo, RelationshipFrom, Relationship,
    db,
)


class UserNode(StructuredNode):
    uid = UniqueIdProperty()
    user_id = IntegerProperty(unique_index=True, required=True)
    username = StringProperty(unique_index=True, required=True)
    display_name = StringProperty()
    is_verified = BooleanProperty(default=False)
    created_at = DateTimeProperty()

    # ── Directed social graph ──────────────────────────────────
    follows = RelationshipTo('UserNode', 'FOLLOWS')
    followed_by = RelationshipFrom('UserNode', 'FOLLOWS')

    # ── Undirected friendship ──────────────────────────────────
    friends = Relationship('UserNode', 'FRIEND_WITH')

    # ── Content ───────────────────────────────────────────────
    created_posts = RelationshipTo('PostNode', 'CREATED')
    liked_posts = RelationshipTo('PostNode', 'LIKED')
    commented_on = RelationshipTo('PostNode', 'COMMENTED_ON')

    # ── Memberships ───────────────────────────────────────────
    member_of = RelationshipTo('GroupNode', 'MEMBER_OF')
    admin_of = RelationshipTo('GroupNode', 'ADMIN_OF')

    def get_friend_recommendations(self, limit=10):
        """Friends-of-friends not already connected."""
        query = """
        MATCH (u:UserNode {user_id: $user_id})-[:FRIEND_WITH]-(friend)-[:FRIEND_WITH]-(fof)
        WHERE NOT (u)-[:FRIEND_WITH]-(fof)
          AND u <> fof
          AND NOT (u)-[:FOLLOWS]->(fof)
        RETURN fof.user_id AS user_id, fof.username AS username,
               count(*) AS mutual_friends
        ORDER BY mutual_friends DESC
        LIMIT $limit
        """
        results, _ = db.cypher_query(
            query, {'user_id': self.user_id, 'limit': limit}
        )
        return [{'user_id': r[0], 'username': r[1], 'mutual_friends': r[2]} for r in results]

    def get_feed_user_ids(self):
        """Return user_ids whose posts belong in this user's feed."""
        query = """
        MATCH (u:UserNode {user_id: $user_id})-[:FOLLOWS|FRIEND_WITH]-(connected)
        RETURN DISTINCT connected.user_id AS user_id
        """
        results, _ = db.cypher_query(query, {'user_id': self.user_id})
        return [r[0] for r in results]

    def get_mutual_friends(self, other_user_id):
        """Return mutual friends between self and another user."""
        query = """
        MATCH (a:UserNode {user_id: $a_id})-[:FRIEND_WITH]-(mutual)-[:FRIEND_WITH]-(b:UserNode {user_id: $b_id})
        RETURN mutual.user_id AS user_id, mutual.username AS username
        """
        results, _ = db.cypher_query(
            query, {'a_id': self.user_id, 'b_id': other_user_id}
        )
        return [{'user_id': r[0], 'username': r[1]} for r in results]


class PostNode(StructuredNode):
    uid = UniqueIdProperty()
    post_id = IntegerProperty(unique_index=True, required=True)
    author_id = IntegerProperty(index=True)
    created_at = DateTimeProperty()

    author = RelationshipFrom('UserNode', 'CREATED')
    liked_by = RelationshipFrom('UserNode', 'LIKED')
    commented_by = RelationshipFrom('UserNode', 'COMMENTED_ON')

    tags = RelationshipTo('TagNode', 'TAGGED_WITH')


class GroupNode(StructuredNode):
    uid = UniqueIdProperty()
    group_id = IntegerProperty(unique_index=True, required=True)
    name = StringProperty()

    members = RelationshipFrom('UserNode', 'MEMBER_OF')
    admins = RelationshipFrom('UserNode', 'ADMIN_OF')


class TagNode(StructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True, required=True)

    posts = RelationshipFrom('PostNode', 'TAGGED_WITH')
