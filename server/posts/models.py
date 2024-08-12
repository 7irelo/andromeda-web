from neomodel import StructuredNode, StringProperty, DateTimeProperty, UniqueIdProperty, RelationshipTo, RelationshipFrom, Relationship
from users.models import User
from django.dispatch import receiver
from django.db.models.signals import post_save
from notifications.models import Notification
from datetime import datetime

class Post(StructuredNode):
    uid = UniqueIdProperty(primary_key=True)
    content = StringProperty()
    created = DateTimeProperty(default_now=True)
    updated = DateTimeProperty(default_now=True)
    creator = RelationshipFrom(User, 'CREATED')
    participants = RelationshipTo(User, 'PARTICIPATED')
    likes = RelationshipTo(User, 'LIKED')
    tags = RelationshipTo('Tag', 'TAGGED')

    def __str__(self):
        return f"Post by {self.creator}: {self.content[:30]}"

class Like(StructuredNode):
    uid = UniqueIdProperty(primary_key=True)
    user = RelationshipFrom(User, 'LIKED')
    post = RelationshipFrom(Post, 'LIKED')
    created_at = DateTimeProperty(default_now=True)

    def __str__(self):
        return f"Like by {self.user.username} on post {self.post.uid}"

    @receiver(post_save, sender='posts.Post')  # Corrected sender reference
    def create_like_notification(sender, instance, created, **kwargs):
        if created:
            Notification.objects.create(
                user=instance.post.creator,
                post=instance.post,
                message=f'{instance.user.username} liked your post.'
            )

class Comment(StructuredNode):
    uid = UniqueIdProperty(primary_key=True)
    text = StringProperty()
    created = DateTimeProperty(default_now=True)
    updated = DateTimeProperty(default_now=True)
    user = RelationshipFrom(User, 'COMMENTED')
    post = RelationshipFrom(Post, 'COMMENTED')

    def __str__(self):
        return f"Comment by {self.user.username} on post {self.post.uid}: {self.text[:50]}"

    @receiver(post_save, sender='posts.Post')  # Corrected sender reference
    def create_comment_notification(sender, instance, created, **kwargs):
        if created:
            Notification.objects.create(
                user=instance.post.creator,
                post=instance.post,
                message=f'{instance.user.username} commented on your post.'
            )

class Tag(StructuredNode):
    uid = UniqueIdProperty(primary_key=True)
    name = StringProperty(unique_index=True)

    def __str__(self):
        return self.name
