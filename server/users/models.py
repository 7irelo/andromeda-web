from neomodel import StructuredNode, StringProperty, EmailProperty, BooleanProperty, DateTimeProperty
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.db import models

class User(StructuredNode, AbstractBaseUser, PermissionsMixin):
    """
    Custom Neo4j-based User model that also integrates with Django's authentication system.
    """
    username = StringProperty(unique=True, required=True)
    email = EmailProperty(unique=True, required=True)
    date_joined = DateTimeProperty(default=timezone.now)
    last_login = DateTimeProperty(default=timezone.now)
    is_active = BooleanProperty(default=True)
    is_staff = BooleanProperty(default=False)
    is_superuser = BooleanProperty(default=False)

    # Django User Manager
    class CustomUserManager(BaseUserManager):
        def create_user(self, username, email, password=None):
            if not email:
                raise ValueError('Users must have an email address')
            if not username:
                raise ValueError('Users must have a username')

            user = User(username=username, email=email)
            user.set_password(password)  # Assuming you have a set_password method
            user.save()
            return user

        def create_superuser(self, username, email, password=None):
            user = self.create_user(username, email, password)
            user.is_superuser = True
            user.is_staff = True
            user.save()
            return user

    objects = CustomUserManager()

    USERNAME_FIELD = 'username'
    EMAIL_FIELD = 'email'
    REQUIRED_FIELDS = ['email']

    def __str__(self):
        return self.username

    # Add a method to handle password hashing
    def set_password(self, raw_password):
        self.password = self.hash_password(raw_password)  # Assuming you implement hash_password

    def check_password(self, raw_password):
        return self.password == self.hash_password(raw_password)

    def hash_password(self, raw_password):
        # Define a password hashing logic or use Django's built-in hasher
        from django.contrib.auth.hashers import make_password, check_password
        if self.password is None:
            return make_password(raw_password)
        return check_password(raw_password, self.password)
