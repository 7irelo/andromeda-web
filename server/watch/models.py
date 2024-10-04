from neomodel import StructuredNode, StringProperty, DateTimeProperty, UniqueIdProperty, RelationshipTo, RelationshipFrom
from users.models import User

class Video(StructuredNode):
    uid = UniqueIdProperty(primary_key=True)
    content = StringProperty()
    created = DateTimeProperty(default_now=True)
    updated = DateTimeProperty(default_now=True)
    creator = RelationshipFrom(User, 'CREATED')
    participants = RelationshipTo(User, 'PARTICIPATED')
    likes = RelationshipTo(User, 'LIKED')
    tags = RelationshipTo('Tag', 'TAGGED')

    def __str__(self):
        return f"Video by {self.creator}: {self.content[:30]}"

class Like(StructuredNode):
    uid = UniqueIdProperty(primary_key=True)
    user = RelationshipFrom(User, 'LIKED')
    video = RelationshipFrom(Video, 'LIKED')
    created_at = DateTimeProperty(default_now=True)

    def __str__(self):
        return f"Like by {self.user.username} on video {self.video.uid}"

class Comment(StructuredNode):
    uid = UniqueIdProperty(primary_key=True)
    text = StringProperty()
    created = DateTimeProperty(default_now=True)
    updated = DateTimeProperty(default_now=True)
    user = RelationshipFrom(User, 'COMMENTED')
    video = RelationshipFrom(Video, 'COMMENTED')

    def __str__(self):
        return f"Comment by {self.user.username} on video {self.video.uid}: {self.text[:50]}"

class Tag(StructuredNode):
    uid = UniqueIdProperty(primary_key=True)
    name = StringProperty(unique_index=True)

    def __str__(self):
        return self.name
