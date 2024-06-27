from django.db import models
from app.models import User

class Item(models.Model):
    host = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    text = models.CharField(max_length=255)  # Increased max_length for text field
    participants = models.ManyToManyField(User, related_name="participated_items", blank=True)
    updated = models.DateTimeField(auto_now=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-updated", "-created"]

    def __str__(self):
        return self.text[:50]  # Display first 50 characters of text field

class ItemComment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="comments")
    text = models.TextField()  # Used TextField for potentially longer comment text
    updated = models.DateTimeField(auto_now=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-updated", "-created"]

    def __str__(self):
        return self.text[:50]  # Display first 50 characters of comment text
