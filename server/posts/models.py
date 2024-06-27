from django.db import models
from app.models import User

class Post(models.Model):
    host = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Host")
    text = models.TextField(max_length=50, verbose_name="Post Text")
    participants = models.ManyToManyField(User, related_name="post_participants", blank=True, verbose_name="Participants")
    updated = models.DateTimeField(auto_now=True, verbose_name="Last Updated")
    created = models.DateTimeField(auto_now_add=True, verbose_name="Date Created")

    class Meta:
        ordering = ["-updated", "-created"]
        verbose_name = "Post"
        verbose_name_plural = "Posts"

    def __str__(self):
        return f"Post by {self.host}: {self.text[:30]}"

class Comment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="User")
    post = models.ForeignKey(Post, on_delete=models.CASCADE, verbose_name="Post")
    text = models.TextField(verbose_name="Comment Text")
    updated = models.DateTimeField(auto_now=True, verbose_name="Last Updated")
    created = models.DateTimeField(auto_now_add=True, verbose_name="Date Created")

    class Meta:
        ordering = ["-updated", "-created"]
        verbose_name = "Comment"
        verbose_name_plural = "Comments"

    def __str__(self):
        return f"Comment by {self.user} on {self.post}: {self.text[:50]}"
