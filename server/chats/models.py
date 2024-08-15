from neomodel import StructuredNode, StringProperty, DateTimeProperty, UniqueIdProperty, RelationshipTo, RelationshipFrom
from users.models import User

class Chat(StructuredNode):
    uid = UniqueIdProperty(primary_key=True)
    text = StringProperty(max_length=255)
    updated = DateTimeProperty(default_now=True)
    created = DateTimeProperty(default_now=True)
    participants = RelationshipTo(User, 'PARTICIPATED_IN')

    def __str__(self):
        return self.text[:50]

class Message(StructuredNode):
    uid = UniqueIdProperty(primary_key=True)
    text = StringProperty()
    updated = DateTimeProperty(default_now=True)
    created = DateTimeProperty(default_now=True)
    user = RelationshipFrom(User, 'SENT')
    chat = RelationshipFrom(Chat, 'HAS_MESSAGE')

    def __str__(self):
        return self.text[:50]
