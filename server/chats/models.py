from django.conf import settings
from django.db import models


class ChatRoom(models.Model):
    TYPE_DIRECT = 'direct'
    TYPE_GROUP = 'group'
    TYPE_CHOICES = [(TYPE_DIRECT, 'Direct'), (TYPE_GROUP, 'Group')]

    room_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default=TYPE_DIRECT)
    name = models.CharField(max_length=255, blank=True)
    avatar = models.ImageField(upload_to='chat_avatars/', null=True, blank=True)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name='chat_rooms', through='ChatMember'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='created_rooms', on_delete=models.SET_NULL, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'chat_rooms'
        ordering = ['-updated_at']

    def __str__(self):
        return self.name or f'Room {self.pk}'

    @property
    def last_message(self):
        return self.messages.order_by('-created_at').first()


class ChatMember(models.Model):
    ROLE_MEMBER = 'member'
    ROLE_ADMIN = 'admin'
    ROLE_CHOICES = [(ROLE_MEMBER, 'Member'), (ROLE_ADMIN, 'Admin')]

    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    last_read_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_members'
        unique_together = ('room', 'user')


class Message(models.Model):
    TYPE_TEXT = 'text'
    TYPE_IMAGE = 'image'
    TYPE_VIDEO = 'video'
    TYPE_FILE = 'file'
    TYPE_CHOICES = [
        (TYPE_TEXT, 'Text'),
        (TYPE_IMAGE, 'Image'),
        (TYPE_VIDEO, 'Video'),
        (TYPE_FILE, 'File'),
    ]

    room = models.ForeignKey(ChatRoom, related_name='messages', on_delete=models.CASCADE)
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='sent_messages', on_delete=models.SET_NULL, null=True
    )
    content = models.TextField(blank=True)
    message_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default=TYPE_TEXT)
    file = models.FileField(upload_to='chat_files/%Y/%m/', null=True, blank=True)
    reply_to = models.ForeignKey(
        'self', null=True, blank=True, related_name='replies', on_delete=models.SET_NULL
    )
    is_edited = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'messages'
        ordering = ['created_at']

    def __str__(self):
        return f'{self.sender} in {self.room}: {self.content[:50]}'

    def get_read_by(self):
        return MessageRead.objects.filter(message=self).select_related('user')


class MessageRead(models.Model):
    message = models.ForeignKey(Message, related_name='reads', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'message_reads'
        unique_together = ('message', 'user')
