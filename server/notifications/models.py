from django.db import models
from users.models import User
from posts.models import Post
from groups.models import Group  # Assuming you have a Group model in your groups app

class Notification(models.Model):
    NOTIFICATION_TYPES = (
        ('birthday', 'Birthday'),
        ('post', 'Post'),
        ('message', 'Message'),
        ('group_message', 'Group Message'),
        ('page_post', 'Page Post'),
        ('software_update', 'Software Update'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    message = models.CharField(max_length=255)
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f'Notification for {self.user.username}: {self.message}'
