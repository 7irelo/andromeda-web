from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Notification
from posts.models import Post
from messages.models import Message  # Assuming you have a Message model
from users.models import User
from datetime import datetime

@receiver(post_save, sender=Post)
def create_post_notification(sender, instance, created, **kwargs):
    if created:
        # Notify friends when a post is created
        for friend in instance.creator.friends.all():
            Notification.objects.create(
                user=friend,
                post=instance,
                message=f'{instance.creator.username} posted a new update.',
                notification_type='post'
            )

@receiver(post_save, sender=Message)
def create_message_notification(sender, instance, created, **kwargs):
    if created:
        # Notify the recipient when a new message is received
        Notification.objects.create(
            user=instance.recipient,
            message=f'You have a new message from {instance.sender.username}.',
            notification_type='message'
        )

@receiver(post_save, sender=User)
def create_birthday_notification(sender, instance, **kwargs):
    # Check if today is the user's birthday
    if instance.date_of_birth and instance.date_of_birth == datetime.today().date():
        for friend in instance.friends.all():
            Notification.objects.create(
                user=friend,
                message=f'Today is {instance.username}\'s birthday!',
                notification_type='birthday'
            )
