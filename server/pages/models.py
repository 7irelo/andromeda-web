from django.db import models
from users.models import User
from posts.models import Post

class Page(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField()
    created = models.DateTimeField(auto_now=True)
    updated = models.DateTimeField(auto_now=True)

    # Relationships
    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='posts')
    followers = models.ManyToManyField(User, related_name='participated_posts')
    likes = models.ManyToManyField(User, related_name='liked_pages')
    posts = post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='posts')

class PagePost(models.Model):
    content = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    creator = models.ForeignKey(Page, on_delete=models.CASCADE, related_name='page_posts')
    participants = models.ManyToManyField(User, related_name='participated_posts')
    likes = models.ManyToManyField(User, related_name='liked_posts')

    def __str__(self):
        return f"Post by {self.creator}: {self.content[:30]}"

