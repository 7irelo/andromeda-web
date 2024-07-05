from django.db import models
from app.models import User

class Chat(models.Model):
    text = models.CharField(max_length=255)  # Increased max_length for text field
    participants = models.ManyToManyField(User, related_name="chats", blank=True)  # Renamed related_name
    updated = models.DateTimeField(auto_now=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-updated", "-created"]

    def __str__(self):
        return self.text[:50]  # Display first 50 characters of text field

class Message(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="messages")  # Added related_name
    text = models.TextField()  # Used TextField for potentially longer message text
    updated = models.DateTimeField(auto_now=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-updated", "-created"]

    def __str__(self):
        return self.text[:50]  # Display first 50 characters of message text
