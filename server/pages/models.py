from django.conf import settings
from django.db import models


class Page(models.Model):
    CATEGORY_BUSINESS = 'business'
    CATEGORY_COMMUNITY = 'community'
    CATEGORY_ENTERTAINMENT = 'entertainment'
    CATEGORY_EDUCATION = 'education'
    CATEGORY_GOVERNMENT = 'government'
    CATEGORY_NONPROFIT = 'nonprofit'
    CATEGORY_OTHER = 'other'
    CATEGORY_CHOICES = [
        (CATEGORY_BUSINESS, 'Business'),
        (CATEGORY_COMMUNITY, 'Community'),
        (CATEGORY_ENTERTAINMENT, 'Entertainment'),
        (CATEGORY_EDUCATION, 'Education'),
        (CATEGORY_GOVERNMENT, 'Government'),
        (CATEGORY_NONPROFIT, 'Non-profit'),
        (CATEGORY_OTHER, 'Other'),
    ]

    name = models.CharField(max_length=255)
    username = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default=CATEGORY_OTHER)
    avatar = models.ImageField(upload_to='pages/avatars/', null=True, blank=True)
    cover_photo = models.ImageField(upload_to='pages/covers/', null=True, blank=True)
    website = models.URLField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    is_verified = models.BooleanField(default=False)
    followers_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='managed_pages', on_delete=models.SET_NULL, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'pages'
        ordering = ['-followers_count']

    def __str__(self):
        return self.name


class PageAdmin(models.Model):
    ROLE_ADMIN = 'admin'
    ROLE_EDITOR = 'editor'
    ROLE_ANALYST = 'analyst'
    ROLE_CHOICES = [(ROLE_ADMIN, 'Admin'), (ROLE_EDITOR, 'Editor'), (ROLE_ANALYST, 'Analyst')]

    page = models.ForeignKey(Page, related_name='admins', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='page_roles', on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_EDITOR)

    class Meta:
        db_table = 'page_admins'
        unique_together = ('page', 'user')


class PageFollow(models.Model):
    page = models.ForeignKey(Page, related_name='followers', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='followed_pages', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'page_follows'
        unique_together = ('page', 'user')
