from django.conf import settings
from django.db import models


class Group(models.Model):
    PRIVACY_PUBLIC = 'public'
    PRIVACY_PRIVATE = 'private'
    PRIVACY_SECRET = 'secret'
    PRIVACY_CHOICES = [
        (PRIVACY_PUBLIC, 'Public'),
        (PRIVACY_PRIVATE, 'Private'),
        (PRIVACY_SECRET, 'Secret'),
    ]

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    cover_photo = models.ImageField(upload_to='groups/covers/', null=True, blank=True)
    avatar = models.ImageField(upload_to='groups/avatars/', null=True, blank=True)
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
