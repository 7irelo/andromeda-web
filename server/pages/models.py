from neomodel import StructuredNode, StructuredRel, StringProperty, DateTimeProperty, UniqueIdProperty, RelationshipTo, RelationshipFrom
from users.models import UserNode  # Assuming you have a UserNode model
from posts.models import PostNode  # Assuming you have a PostNode model

class CreatedRel(StructuredRel):
    created = DateTimeProperty(default_now=True)

class PageNode(StructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True, required=True)
    description = StringProperty()
    created = DateTimeProperty(default_now=True)
    updated = DateTimeProperty(default_now=True)

    # Relationships
    creator = RelationshipTo(UserNode, 'CREATED_BY', model=CreatedRel)
    followers = RelationshipFrom(UserNode, 'FOLLOWS')
    likes = RelationshipFrom(UserNode, 'LIKES')
    posts = RelationshipTo('PostNode', 'HAS_POST')

class PagePostRel(StructuredRel):
    created = DateTimeProperty(default_now=True)

class PagePostNode(StructuredNode):
    uid = UniqueIdProperty()
    page = RelationshipTo(PageNode, 'BELONGS_TO')
    post = RelationshipTo(PostNode, 'INCLUDES', model=PagePostRel)
