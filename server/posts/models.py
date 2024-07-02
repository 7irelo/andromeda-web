from django.db import models
from users.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from notifications.models import Notification

class Post(models.Model):
    creator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Creator")
    text = models.TextField(max_length=50, verbose_name="Post Text")
    participants = models.ManyToManyField(User, related_name="post_participants", blank=True, verbose_name="Participants")
    likes = models.ManyToManyField(User, related_name="post_likes", blank=True, verbose_name="Likes")
    updated = models.DateTimeField(auto_now=True, verbose_name="Last Updated")
    created = models.DateTimeField(auto_now_add=True, verbose_name="Date Created")

    class Meta:
        ordering = ["-updated", "-created"]
        verbose_name = "Post"
        verbose_name_plural = "Posts"

    def __str__(self):
        return f"Post by {self.creator}: {self.text[:30]}"

class Like(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='likes')
    created_at = models.DateTimeField(auto_now_add=True)
    
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

@receiver(post_save, sender=Like)
def create_like_notification(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            user=instance.post.user,
            post=instance.post,
            message=f'{instance.user.username} liked your post.'
        )

@receiver(post_save, sender=Comment)
def create_comment_notification(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            user=instance.post.user,
            post=instance.post,
            message=f'{instance.user.username} commented on your post.'
        )
