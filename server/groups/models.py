import hashlib

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.validators import RandomFilename


class Group(models.Model):
    PRIVACY_PUBLIC = 'public'
    PRIVACY_PRIVATE = 'private'
    PRIVACY_SECRET = 'secret'  # noqa: S105 - a privacy level, not a credential
    PRIVACY_CHOICES = [
        (PRIVACY_PUBLIC, 'Public'),
        (PRIVACY_PRIVATE, 'Private'),
        (PRIVACY_SECRET, 'Secret'),
    ]

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    cover_photo = models.ImageField(upload_to=RandomFilename('public/groups/covers'), null=True, blank=True)
    avatar = models.ImageField(upload_to=RandomFilename('public/groups/avatars'), null=True, blank=True)
    privacy = models.CharField(max_length=10, choices=PRIVACY_CHOICES, default=PRIVACY_PUBLIC)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='created_groups', on_delete=models.SET_NULL, null=True
    )
    members_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'groups'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class GroupMember(models.Model):
    ROLE_MEMBER = 'member'
    ROLE_MODERATOR = 'moderator'
    ROLE_ADMIN = 'admin'
    ROLE_CHOICES = [
        (ROLE_MEMBER, 'Member'),
        (ROLE_MODERATOR, 'Moderator'),
        (ROLE_ADMIN, 'Admin'),
    ]

    group = models.ForeignKey(Group, related_name='memberships', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='group_memberships', on_delete=models.CASCADE)
    role = models.CharField(max_length=15, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'group_members'
        unique_together = ('group', 'user')


class GroupJoinRequest(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_ACCEPTED = 'accepted'
    STATUS_DECLINED = 'declined'

    group = models.ForeignKey(Group, related_name='join_requests', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='group_join_requests', on_delete=models.CASCADE)
    status = models.CharField(max_length=10, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'group_join_requests'
        unique_together = ('group', 'user')


class GroupBan(models.Model):
    """A banned user can't rejoin, request to join or redeem an invite until unbanned."""

    group = models.ForeignKey(Group, related_name='bans', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='group_bans', on_delete=models.CASCADE)
    banned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='+', on_delete=models.SET_NULL, null=True
    )
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'group_bans'
        unique_together = ('group', 'user')
        ordering = ['-created_at']


class GroupRule(models.Model):
    group = models.ForeignKey(Group, related_name='rules', on_delete=models.CASCADE)
    position = models.PositiveSmallIntegerField(default=0)
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    class Meta:
        db_table = 'group_rules'
        ordering = ['position', 'id']


class GroupPinnedPost(models.Model):
    group = models.ForeignKey(Group, related_name='pins', on_delete=models.CASCADE)
    post = models.ForeignKey('posts.Post', related_name='group_pins', on_delete=models.CASCADE)
    pinned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='+', on_delete=models.SET_NULL, null=True
    )
    pinned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'group_pinned_posts'
        unique_together = ('group', 'post')
        ordering = ['-pinned_at']


class GroupInvite(models.Model):
    """
    A shareable join link. Only a SHA-256 digest of the token is stored, so a
    database leak doesn't hand out working links; the raw token is shown once.
    """

    group = models.ForeignKey(Group, related_name='invites', on_delete=models.CASCADE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='+', on_delete=models.SET_NULL, null=True
    )
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    uses_count = models.PositiveIntegerField(default=0)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'group_invites'
        ordering = ['-created_at']

    @staticmethod
    def hash_token(token):
        return hashlib.sha256(token.encode()).hexdigest()

    @property
    def is_usable(self):
        return (
            self.revoked_at is None
            and self.expires_at > timezone.now()
            and (self.max_uses is None or self.uses_count < self.max_uses)
        )
