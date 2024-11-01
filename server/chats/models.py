from django.db import models
from users.models import User

class Chat(models.Model):
    text = models.CharField(max_length=255)
    updated = models.DateTimeField(auto_now=True)
    created = models.DateTimeField(auto_now_add=True)
    participants = models.ManyToManyField(User, related_name='chats')

    def __str__(self):
        return self.text[:50]

class Message(models.Model):
    text = models.TextField()
    updated = models.DateTimeField(auto_now=True)
    created = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='messages')
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='messages')

    def __str__(self):
        return self.text[:50]
