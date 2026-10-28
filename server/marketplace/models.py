from django.conf import settings
from django.db import models

from core.validators import RandomFilename


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    icon = models.CharField(max_length=50, blank=True)
    parent = models.ForeignKey('self', null=True, blank=True, related_name='children', on_delete=models.SET_NULL)

    class Meta:
        db_table = 'marketplace_categories'
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name


class Listing(models.Model):
    CONDITION_NEW = 'new'
    CONDITION_LIKE_NEW = 'like_new'
    CONDITION_GOOD = 'good'
    CONDITION_FAIR = 'fair'
    CONDITION_POOR = 'poor'
    CONDITION_CHOICES = [
        (CONDITION_NEW, 'New'),
        (CONDITION_LIKE_NEW, 'Like New'),
        (CONDITION_GOOD, 'Good'),
        (CONDITION_FAIR, 'Fair'),
        (CONDITION_POOR, 'Poor'),
    ]

    STATUS_ACTIVE = 'active'
    STATUS_RESERVED = 'reserved'
    STATUS_SOLD = 'sold'
    STATUS_DRAFT = 'draft'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_RESERVED, 'Reserved'),
        (STATUS_SOLD, 'Sold'),
        (STATUS_DRAFT, 'Draft'),
    ]
    # What other users can browse. Sold and draft listings are the seller's alone.
    PUBLIC_STATUSES = (STATUS_ACTIVE, STATUS_RESERVED)

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='listings', on_delete=models.CASCADE
    )
    title = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    condition = models.CharField(max_length=10, choices=CONDITION_CHOICES, default=CONDITION_GOOD)
    category = models.ForeignKey(Category, related_name='listings', on_delete=models.SET_NULL, null=True)
    location = models.CharField(max_length=255, blank=True)
    # Snapped to a ~1 km grid on save (see geo.py); never shown to others at this precision.
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    # Set by the moderation pipeline; 'removed' hides it from everyone but the author.
    moderation_status = models.CharField(max_length=10, default='ok', db_index=True,
                                         choices=[('ok', 'OK'), ('review', 'In review'), ('removed', 'Removed')])
    views_count = models.PositiveIntegerField(default=0)
    likes_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'marketplace_listings'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['latitude', 'longitude'], name='listing_geo_idx')]

    def __str__(self):
        return f'{self.title} – ${self.price}'


class ListingImage(models.Model):
    listing = models.ForeignKey(Listing, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to=RandomFilename('public/marketplace'))
    is_primary = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'marketplace_images'
        ordering = ['order']


class ListingLike(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    listing = models.ForeignKey(Listing, related_name='liked_by', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'marketplace_likes'
        unique_together = ('user', 'listing')


class Review(models.Model):
    listing = models.ForeignKey(Listing, related_name='reviews', on_delete=models.CASCADE)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'marketplace_reviews'
        unique_together = ('listing', 'reviewer')
        ordering = ['-created_at']
