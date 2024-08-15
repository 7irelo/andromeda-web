from neomodel import StructuredNode, StringProperty, UniqueIdProperty, BooleanProperty, DateTimeProperty, RelationshipTo
from django.contrib.auth.hashers import make_password, check_password

class User(StructuredNode):
    uid = UniqueIdProperty(primary_key=True)
    username = StringProperty(unique_index=True, required=True)
    first_name = StringProperty()
    last_name = StringProperty()
    email = StringProperty(unique_index=True)
    avatar = StringProperty(default='avatars/profile.png')
    bio = StringProperty()
    password = StringProperty(required=True)
    is_staff = BooleanProperty(default=False)
    is_active = BooleanProperty(default=True)
    is_superuser = BooleanProperty(default=False)
    last_login = DateTimeProperty()
    date_joined = DateTimeProperty()

    friends = RelationshipTo('User', 'FRIEND')

    def __str__(self):
        return self.username

    def get_full_name(self):
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name if full_name else self.username

    def get_short_name(self):
        return self.first_name if self.first_name else self.username

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    def has_perm(self, perm, obj=None):
        return self.is_superuser

    def has_module_perms(self, app_label):
        return self.is_superuser
