from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Extended user model for Andromeda."""

    bio = models.TextField(blank=True, default='')
    avatar = models.ImageField(upload_to='avatars/%Y/%m/', null=True, blank=True)
    cover_photo = models.ImageField(upload_to='covers/%Y/%m/', null=True, blank=True)
    location = models.CharField(max_length=120, blank=True)
    website = models.URLField(blank=True)
    birth_date = models.DateField(null=True, blank=True)
    is_verified = models.BooleanField(default=False)

    # Denormalised counters (updated by signals)
    followers_count = models.PositiveIntegerField(default=0)
    following_count = models.PositiveIntegerField(default=0)
    friends_count = models.PositiveIntegerField(default=0)
    posts_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users'
        ordering = ['-created_at']

    def __str__(self):
        return self.username

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'.strip() or self.username

    @property
    def avatar_url(self):
        if self.avatar:
            return self.avatar.url
        return '/static/default_avatar.png'


class FriendRequest(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_ACCEPTED = 'accepted'
    STATUS_DECLINED = 'declined'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACCEPTED, 'Accepted'),
        (STATUS_DECLINED, 'Declined'),
    ]

    sender = models.ForeignKey(User, related_name='sent_requests', on_delete=models.CASCADE)
    receiver = models.ForeignKey(User, related_name='received_requests', on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'friend_requests'
        unique_together = ('sender', 'receiver')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.sender} → {self.receiver} ({self.status})'


class Follow(models.Model):
    """A follows B (directed)."""
    follower = models.ForeignKey(User, related_name='following_set', on_delete=models.CASCADE)
    following = models.ForeignKey(User, related_name='followers_set', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'follows'
        unique_together = ('follower', 'following')

    def __str__(self):
        return f'{self.follower} follows {self.following}'


class Block(models.Model):
    blocker = models.ForeignKey(User, related_name='blocking_set', on_delete=models.CASCADE)
    blocked = models.ForeignKey(User, related_name='blocked_by_set', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'blocks'
        unique_together = ('blocker', 'blocked')
