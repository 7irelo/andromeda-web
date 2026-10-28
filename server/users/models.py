from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q

from core.validators import RandomFilename


class User(AbstractUser):
    """Extended user model for Andromeda."""

    # Override AbstractUser.email to enforce uniqueness across all accounts
    email = models.EmailField(unique=True, blank=False)

    bio = models.TextField(blank=True, default='')
    avatar = models.ImageField(upload_to=RandomFilename('public/avatars'), null=True, blank=True)
    cover_photo = models.ImageField(upload_to=RandomFilename('public/covers'), null=True, blank=True)
    location = models.CharField(max_length=120, blank=True)
    website = models.URLField(blank=True)
    birth_date = models.DateField(null=True, blank=True)
    is_verified = models.BooleanField(default=False)  # the staff-granted verified badge
    email_verified = models.BooleanField(default=False)
    # Opt out of AI features: content isn't indexed for semantic search or
    # used for training, and AI features are switched off for this account.
    ai_opt_out = models.BooleanField(default=False)
    # Moderation: a suspended account can't sign in until this time passes.
    suspended_until = models.DateTimeField(null=True, blank=True)
    # Account deletion is delayed so a mistaken or hijacked request can be undone.
    deletion_scheduled_at = models.DateTimeField(null=True, blank=True)

    # Denormalised counters (updated by signals)
    friends_count = models.PositiveIntegerField(default=0)
    posts_count = models.PositiveIntegerField(default=0)

    # Privacy settings
    PRIVACY_EVERYONE = 'everyone'
    PRIVACY_FRIENDS = 'friends'
    PRIVACY_PRIVATE = 'private'

    PROFILE_PRIVACY_CHOICES = [
        ('everyone', 'Everyone'),
        ('friends', 'Friends'),
        ('private', 'Only Me'),
    ]
    MESSAGE_PRIVACY_CHOICES = [
        ('everyone', 'Everyone'),
        ('friends', 'Friends'),
        ('nobody', 'Nobody'),
    ]
    FRIEND_REQUEST_PRIVACY_CHOICES = [
        ('everyone', 'Everyone'),
        ('friends_of_friends', 'Friends of Friends'),
        ('nobody', 'Nobody'),
    ]
    POST_PRIVACY_CHOICES = [
        ('public', 'Public'),
        ('friends', 'Friends'),
        ('private', 'Only Me'),
    ]

    privacy_profile = models.CharField(max_length=20, choices=PROFILE_PRIVACY_CHOICES, default='everyone')
    privacy_messages = models.CharField(max_length=20, choices=MESSAGE_PRIVACY_CHOICES, default='everyone')
    privacy_friend_requests = models.CharField(max_length=20, choices=FRIEND_REQUEST_PRIVACY_CHOICES, default='everyone')
    privacy_friends_list = models.CharField(max_length=20, choices=PROFILE_PRIVACY_CHOICES, default='everyone')
    default_post_privacy = models.CharField(max_length=20, choices=POST_PRIVACY_CHOICES, default='public')
    show_online_status = models.BooleanField(default=True)
    searchable = models.BooleanField(default=True)

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
        constraints = [
            models.CheckConstraint(
                condition=~Q(sender=models.F('receiver')),
                name='no_self_friend_request',
            ),
        ]

    def __str__(self):
        return f'{self.sender} → {self.receiver} ({self.status})'


class Block(models.Model):
    blocker = models.ForeignKey(User, related_name='blocking_set', on_delete=models.CASCADE)
    blocked = models.ForeignKey(User, related_name='blocked_by_set', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'blocks'
        unique_together = ('blocker', 'blocked')


class UserSession(models.Model):
    """
    One signed-in device. The id travels as the `sid` claim in the refresh
    token and survives rotation, so a device keeps one row however often it
    refreshes, and revoking the row ends that device's session.
    """

    id = models.UUIDField(primary_key=True)
    user = models.ForeignKey(User, related_name='sessions', on_delete=models.CASCADE)
    user_agent = models.CharField(max_length=200, blank=True)
    # Only a coarse network prefix is kept, never the full address.
    ip_prefix = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-last_seen_at']
        indexes = [models.Index(fields=['user', 'revoked_at'])]


class MFADevice(models.Model):
    """TOTP second factor. The secret is encrypted at rest; recovery codes are stored hashed."""

    user = models.OneToOneField(User, related_name='mfa', on_delete=models.CASCADE)
    secret_encrypted = models.TextField()
    enabled = models.BooleanField(default=False)
    # The last accepted time step, so a code can't be replayed inside its window.
    last_step = models.BigIntegerField(default=0)
    recovery_codes = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    enabled_at = models.DateTimeField(null=True, blank=True)


class ConsentRecord(models.Model):
    """Append-only record of what the member agreed to (or withdrew), and when."""

    KIND_TERMS = 'terms'
    KIND_PRIVACY = 'privacy'
    KIND_AI = 'ai_features'
    KIND_CHOICES = [(KIND_TERMS, 'Terms of service'), (KIND_PRIVACY, 'Privacy policy'), (KIND_AI, 'AI features')]

    user = models.ForeignKey(User, related_name='consents', on_delete=models.CASCADE)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    version = models.CharField(max_length=20)
    granted = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class DataExport(models.Model):
    """A downloadable archive of everything a member has on Andromeda (POPIA/GDPR access request)."""

    STATUS_PENDING = 'pending'
    STATUS_READY = 'ready'
    STATUS_FAILED = 'failed'

    user = models.ForeignKey(User, related_name='data_exports', on_delete=models.CASCADE)
    status = models.CharField(max_length=10, default=STATUS_PENDING)
    file = models.FileField(upload_to=RandomFilename('private/exports'), null=True, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
