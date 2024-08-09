from neomodel import StructuredNode, StringProperty, FloatProperty, DateTimeProperty, RelationshipTo, RelationshipFrom, UniqueIdProperty
from users.models import User
from notifications.models import Notification
from datetime import datetime

class ProductTag(StructuredNode):
    name = StringProperty(unique_index=True, required=True)

class Product(StructuredNode):
    uid = UniqueIdProperty()
    creator = RelationshipTo(User, 'CREATED_BY')
    name = StringProperty(required=True)
    description = StringProperty()
    price = FloatProperty(required=True)
    participants = RelationshipTo(User, 'PARTICIPATED_BY')
    likes = RelationshipTo(User, 'LIKED_BY')
    tags = RelationshipTo(ProductTag, 'HAS_TAG')
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
        Notification(user=self.product.creator, product=self.product, message=f'{self.user.username} commented on your product.')

# Signals are not supported in Neo4j so you’ll need to manually create notifications as shown in ProductComment.
