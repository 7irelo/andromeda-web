from django.db import models
from users.models import User
from posts.models import Tag
from datetime import datetime

class Product(models.Model):
    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    price = models.FloatField()
    participants = models.ManyToManyField(User, related_name='participated_products')
    likes = models.ManyToManyField(User, related_name='liked_products')
    tags = models.ManyToManyField(Tag, related_name='products')
    updated = models.DateTimeField(auto_now=True)
    created = models.DateTimeField(auto_now_add=True)

class ProductLike(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='product_likes')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='product_likes')
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Like by {self.user.username} on post {self.post.uid}"

class ProductComment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='product_comments')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='comments')
    text = models.TextField()
    updated = models.DateTimeField(auto_now=True)
    created = models.DateTimeField(auto_now_add=True)