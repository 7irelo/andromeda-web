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


class Post(models.Model):
    host = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    text = models.CharField(max_length=50)
    participants = models.ManyToManyField(User, related_name="participants", blank=True)
    updated = models.DateTimeField(auto_now=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-updated", "-created"]

    def __str__(self):
        return self.text

class Message(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey(Room, on_delete=models.CASCADE)
    text = models.TextField()
    updated = models.DateTimeField(auto_now=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-updated", "-created"]

    def __str__(self):
        return self.text[0:50]
