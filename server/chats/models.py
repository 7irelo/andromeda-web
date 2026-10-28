from django.conf import settings
from django.db import models

from core.validators import RandomFilename


class ChatRoom(models.Model):
    TYPE_DIRECT = 'direct'
    TYPE_GROUP = 'group'
    TYPE_CHOICES = [(TYPE_DIRECT, 'Direct'), (TYPE_GROUP, 'Group')]

    room_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default=TYPE_DIRECT)
    name = models.CharField(max_length=255, blank=True)
    avatar = models.ImageField(upload_to=RandomFilename('public/chat_avatars'), null=True, blank=True)
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
    TYPE_VOICE = 'voice'
    TYPE_CHOICES = [
        (TYPE_TEXT, 'Text'),
        (TYPE_IMAGE, 'Image'),
        (TYPE_VIDEO, 'Video'),
        (TYPE_FILE, 'File'),
        (TYPE_VOICE, 'Voice note'),
    ]

    TRANSCRIPT_NONE = ''
    TRANSCRIPT_PENDING = 'pending'
    TRANSCRIPT_DONE = 'done'
    TRANSCRIPT_FAILED = 'failed'
    TRANSCRIPT_CHOICES = [
        (TRANSCRIPT_NONE, 'None'),
        (TRANSCRIPT_PENDING, 'Pending'),
        (TRANSCRIPT_DONE, 'Done'),
        (TRANSCRIPT_FAILED, 'Failed'),
    ]

    room = models.ForeignKey(ChatRoom, related_name='messages', on_delete=models.CASCADE)
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='sent_messages', on_delete=models.SET_NULL, null=True
    )
    content = models.TextField(blank=True)
    message_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default=TYPE_TEXT)
    file = models.FileField(upload_to=RandomFilename('private/chat_files'), null=True, blank=True)
    reply_to = models.ForeignKey(
        'self', null=True, blank=True, related_name='replies', on_delete=models.SET_NULL
    )
    is_edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    # Voice notes: length read from the container, transcript filled in by a Celery task.
    duration_s = models.FloatField(null=True, blank=True)
    transcript = models.TextField(blank=True)
    transcript_status = models.CharField(max_length=10, choices=TRANSCRIPT_CHOICES, blank=True,
                                         default=TRANSCRIPT_NONE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'messages'
        ordering = ['created_at']
        indexes = [models.Index(fields=['room', 'created_at'])]

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


class MessageReaction(models.Model):
    """One reaction per user per message, from a small fixed set."""

    REACTION_CHOICES = [
        ('like', 'Like'), ('love', 'Love'), ('haha', 'Haha'),
        ('wow', 'Wow'), ('sad', 'Sad'), ('angry', 'Angry'),
    ]
    REACTIONS = {key for key, _ in REACTION_CHOICES}

    message = models.ForeignKey(Message, related_name='reactions', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    reaction = models.CharField(max_length=10, choices=REACTION_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'message_reactions'
        unique_together = ('message', 'user')


class ReplySuggestionEvent(models.Model):
    """
    Implicit feedback on smart replies, for acceptance rates and preference data.

    Only a keyed hash of the suggestion is stored, never its text. ``shown``
    rows are written when suggestions are served; the other actions must refer
    to a hash that was shown to the same user in the same room.
    """

    ACTION_SHOWN = 'shown'
    ACTION_ACCEPTED = 'accepted'   # sent verbatim
    ACTION_EDITED = 'edited'       # tapped, changed, then sent
    ACTION_DISMISSED = 'dismissed'
    ACTION_CHOICES = [(ACTION_SHOWN, 'Shown'), (ACTION_ACCEPTED, 'Accepted'), (ACTION_EDITED, 'Edited'),
                      (ACTION_DISMISSED, 'Dismissed')]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='+', on_delete=models.CASCADE)
    room = models.ForeignKey(ChatRoom, related_name='+', on_delete=models.CASCADE)
    suggestion_hash = models.CharField(max_length=64)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    variant = models.CharField(max_length=20)
    # The newest message the suggestions answered, so one set of suggestions can be grouped.
    anchor_message_id = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'reply_suggestion_events'
        indexes = [models.Index(fields=['user', 'room', 'suggestion_hash']),
                   models.Index(fields=['variant', 'action'])]


class SeedReplySuggestion(models.Model):
    """
    Suggestion text for synthetic (seed) conversations only, so offline
    preference pairs can be built from them. Written only when
    REPLY_SFT_CAPTURE_SEED_TEXT is on and every member of the room is a seed
    account; real users' suggestion text is never stored.
    """

    suggestion_hash = models.CharField(max_length=64, unique=True)
    text = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'seed_reply_suggestions'
