from django.db import models
from users.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from notifications.models import Notification

class Product(models.Model):
    """
    Represents a product listed by a user in the marketplace.
    """
    creator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Creator")
    name = models.CharField(max_length=255, verbose_name="Product Name")
    description = models.TextField(verbose_name="Product Description")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Price")
    participants = models.ManyToManyField(User, related_name="product_participants", blank=True, verbose_name="Participants")
    likes = models.ManyToManyField(User, related_name="product_likes", blank=True, verbose_name="Likes")
    tags = models.ManyToManyField('ProductTag', related_name='products', blank=True, verbose_name="Tags")
    updated = models.DateTimeField(auto_now=True, verbose_name="Last Updated")
    created = models.DateTimeField(auto_now_add=True, verbose_name="Date Created")

    class Meta:
        ordering = ["-updated", "-created"]
        verbose_name = "Product"
        verbose_name_plural = "Products"

    def __str__(self):
        return f"Product by {self.creator}: {self.name[:30]}"

class ProductLike(models.Model):
    """
    Represents a like on a product by a user.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='likes')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Like by {self.user.username} on product {self.product.id}"

@receiver(post_save, sender=ProductLike)
def create_product_like_notification(sender, instance, created, **kwargs):
    """
    Create a notification when a product is liked.
    """
    if created:
        Notification.objects.create(
            user=instance.product.creator,
            product=instance.product,
            message=f'{instance.user.username} liked your product.'
        )

class ProductComment(models.Model):
    """
    Represents a comment on a product by a user.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="User")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="Product")
    text = models.TextField(verbose_name="Comment Text")
    updated = models.DateTimeField(auto_now=True, verbose_name="Last Updated")
    created = models.DateTimeField(auto_now_add=True, verbose_name="Date Created")

    class Meta:
        ordering = ["-updated", "-created"]
        verbose_name = "Product Comment"
        verbose_name_plural = "Product Comments"

    def __str__(self):
        return f"Comment by {self.user.username} on product {self.product.id}: {self.text[:50]}"

@receiver(post_save, sender=ProductComment)
def create_product_comment_notification(sender, instance, created, **kwargs):
    """
    Create a notification when a comment is made on a product.
    """
    if created:
        Notification.objects.create(
            user=instance.product.creator,
            product=instance.product,
            message=f'{instance.user.username} commented on your product.'
        )

class ProductTag(models.Model):
    """
    Represents a tag that can be associated with a product.
    """
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name
