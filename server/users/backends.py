from django.contrib.auth.backends import BaseBackend
from .models import UserNode

class Neo4jBackend(BaseBackend):
    """
    Custom authentication backend to authenticate users with Neo4j.
    """

    def authenticate(self, request, username=None, password=None):
        """
        Authenticate a user against the Neo4j database using the User model.
        """
        try:
            # Attempt to retrieve the user by username
            user = UserNode.nodes.get(username=username)
            # Check the password
            if user.check_password(password):
                return user
        except UserNode.DoesNotExist:
            # Return None if the user does not exist
            return None

    def get_user(self, user_id):
        """
        Retrieve a user by their unique ID (uid).
        """
        try:
            return UserNode.nodes.get(uid=user_id)
        except User.DoesNotExist:
            return None
