from neomodel import StructuredNode, StringProperty, UniqueIdProperty, RelationshipTo, RelationshipFrom
from django.contrib.auth.models import AbstractUser
from neomodel import config

# Neo4j connection (ensure this is set in your environment or settings)
config.DATABASE_URL = 'bolt://neo4j:password@localhost:7687'

class User(StructuredNode, AbstractUser):
    uid = UniqueIdProperty(primary_key=True)
    first_name = StringProperty()
    last_name = StringProperty()
    username = StringProperty(unique_index=True, required=True)
    email = StringProperty(unique_index=True)
    avatar = StringProperty(default='avatars/profile.png')
    bio = StringProperty()
    friends = RelationshipTo('User', 'FRIEND')

    def __str__(self):
        return self.username

    def get_full_name(self):
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name if full_name else self.username

    def get_short_name(self):
        return self.first_name if self.first_name else self.username
