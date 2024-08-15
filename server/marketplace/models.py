from neomodel import StructuredNode, StringProperty, FloatProperty, DateTimeProperty, RelationshipTo, RelationshipFrom, UniqueIdProperty
from users.models import User
from posts.models import Tag
from datetime import datetime

class Product(StructuredNode):
    uid = UniqueIdProperty()
    creator = RelationshipTo(User, 'CREATED_BY')
    name = StringProperty(required=True)
    description = StringProperty()
    price = FloatProperty(required=True)
    participants = RelationshipTo(User, 'PARTICIPATED_BY')
    likes = RelationshipTo(User, 'LIKED_BY')
    tags = RelationshipTo(Tag, 'HAS_TAG')
    updated = DateTimeProperty(default=datetime.utcnow)
    created = DateTimeProperty(default=datetime.utcnow)

class ProductLike(StructuredNode):
    user = RelationshipTo(User, 'LIKED_BY')
    product = RelationshipFrom(Product, 'HAS_LIKE')
    created_at = DateTimeProperty(default=datetime.utcnow)

class ProductComment(StructuredNode):
    user = RelationshipTo(User, 'COMMENTED_BY')
    product = RelationshipFrom(Product, 'HAS_COMMENT')
    text = StringProperty(required=True)
    updated = DateTimeProperty(default=datetime.utcnow)
    created = DateTimeProperty(default=datetime.utcnow)

    def create_product_comment_notification(self):
        # Implement logic to create notifications here.
        pass
