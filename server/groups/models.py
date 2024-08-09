from neomodel import (
    StructuredNode, StringProperty, DateTimeProperty, UniqueIdProperty, RelationshipTo, RelationshipFrom, BooleanProperty
)
from users.models import User

class Group(StructuredNode):
    uid = UniqueIdProperty(primary_key=True)
    name = StringProperty(unique=True, required=True)
    description = StringProperty()
    created = DateTimeProperty(default_now=True)
    updated = DateTimeProperty(default_now=True)
    members = RelationshipTo(User, 'MEMBER_OF')

    def __str__(self):
        return self.name

class GroupMessage(StructuredNode):
    uid = UniqueIdProperty(primary_key=True)
    text = StringProperty(required=True)
    created = DateTimeProperty(default_now=True)
    updated = DateTimeProperty(default_now=True)
    group = RelationshipFrom('Group', 'HAS_MESSAGE')
    sender = RelationshipFrom(User, 'SENT_MESSAGE')

    def __str__(self):
        return self.text[:50]

class GroupMembership(StructuredNode):
    uid = UniqueIdProperty(primary_key=True)
    user = RelationshipFrom(User, 'IS_MEMBER')
    group = RelationshipFrom(Group, 'HAS_MEMBER')
    is_admin = BooleanProperty(default=False)
    created = DateTimeProperty(default_now=True)

    def __str__(self):
        return f'{self.user} in {self.group}'
