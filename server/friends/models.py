from django.db import models
# from django.contrib.auth.models import User
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    email = models.EmailField(unique=True, null=True)
    bio = models.TextField(null=True)

    # avatar = models.ImageField(null=True, default="profile.png")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    pass
