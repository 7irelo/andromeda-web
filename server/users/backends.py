from django.contrib.auth.backends import BaseBackend
from .models import User

class Neo4jBackend(BaseBackend):
    """
    Custom authentication backend to authenticate users with Neo4j.
    """
    def authenticate(self, request, username=None, password=None):
        try:
            # Attempt to retrieve the user by username
            user = User.nodes.get(username=username)
            # Check the password
            if user.check_password(password):
                return user
        except User.DoesNotExist:
            # Return None if the user does not exist
            return None

    def get_user(self, user_id):
        try:
            return User.nodes.get(id=user_id)
        except User.DoesNotExist:
            return None
