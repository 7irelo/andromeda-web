from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    username = models.CharField(max_length=150, unique=True, primary_key=True)
    email = models.EmailField(unique=True, null=True, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True, default='avatars/profile.png')
    bio = models.TextField(null=True, blank=True)
    friends = models.ManyToManyField('self', through='Friendship', symmetrical=False, related_name='friend_set')

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.username

    def get_full_name(self):
        """
        Return the full name of the user.
        """
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name if full_name else self.username

    def get_short_name(self):
        """
        Return the short name for the user.
        """
        return self.first_name if self.first_name else self.username

class Friendship(models.Model):
    from_user = models.ForeignKey(User, related_name='from_friend', on_delete=models.CASCADE)
    to_user = models.ForeignKey(User, related_name='to_friend', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('from_user', 'to_user')
        indexes = [
            models.Index(fields=['from_user', 'to_user']),
        ]

    def __str__(self):
        return f"Friendship from {self.from_user.username} to {self.to_user.username}"
