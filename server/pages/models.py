from neomodel import StructuredNode, StringProperty, DateTimeProperty, UniqueIdProperty, RelationshipTo, RelationshipFrom, StructuredRel
from users.models import User
from posts.models import Post

class CreatedRel(StructuredRel):
    created = DateTimeProperty(default_now=True)

class Page(StructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True, required=True)
    description = StringProperty()
    created = DateTimeProperty(default_now=True)
    updated = DateTimeProperty(default_now=True)

    # Relationships
    creator = RelationshipTo(User, 'CREATED_BY', model=CreatedRel)
    followers = RelationshipFrom(User, 'FOLLOWS')
    likes = RelationshipFrom(User, 'LIKES')
    posts = RelationshipTo(Post, 'HAS_POST')

class PagePostRel(StructuredRel):
    created = DateTimeProperty(default_now=True)

class PagePost(StructuredNode):
    uid = UniqueIdProperty()
    page = RelationshipTo(Page, 'BELONGS_TO')
    post = RelationshipTo(Post, 'INCLUDES', model=PagePostRel)
