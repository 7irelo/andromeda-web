from collections import Counter

from rest_framework import serializers

from users.models import User
from imaging import variants
from users.serializers import BASIC_FIELDS
from .models import ChatRoom, ChatMember, Message, MessageReaction

DELETED_TEXT = 'message deleted'


class ChatUserSerializer(serializers.ModelSerializer):
    """
    Basic public fields only (what anyone who can see the user at all gets),
    so message lists and WebSocket frames don't run per-message privacy and
    friendship queries.
    """

    avatar_url = serializers.SerializerMethodField()
    avatar_variants = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = BASIC_FIELDS
        read_only_fields = fields

    def get_avatar_url(self, obj):
        if not obj.avatar:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.avatar.url) if request else obj.avatar.url

    def get_avatar_variants(self, obj):
        return variants.urls(obj.avatar, variants.AVATAR_WIDTHS, self.context.get('request'))


class MessageSerializer(serializers.ModelSerializer):
    sender = ChatUserSerializer(read_only=True)
    reply_to_data = serializers.SerializerMethodField()
    read_by_count = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    reactions = serializers.SerializerMethodField()
    my_reaction = serializers.SerializerMethodField()
    content = serializers.CharField(max_length=5000, allow_blank=True, required=False)

    class Meta:
        model = Message
        fields = [
            'id', 'room', 'sender', 'content', 'message_type',
            'file', 'file_url', 'reply_to', 'reply_to_data',
            'is_edited', 'edited_at', 'is_deleted', 'read_by_count',
            'duration_s', 'transcript', 'transcript_status',
            'reactions', 'my_reaction',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'sender', 'is_edited', 'edited_at', 'is_deleted', 'duration_s',
            'transcript', 'transcript_status', 'created_at', 'updated_at',
        ]
        # Attachments are private: clients get an authenticated URL, never the storage path.
        extra_kwargs = {'file': {'write_only': True}}

    def validate(self, attrs):
        if self.instance is not None:
            # Edits may only change the text.
            attrs = {k: v for k, v in attrs.items() if k == 'content'}
        return attrs

    def to_representation(self, obj):
        data = super().to_representation(obj)
        if obj.is_deleted:
            # Tombstone: keep the row so replies and ordering still make sense.
            data.update(content='', file_url=None, transcript='', duration_s=None, reactions=[], my_reaction=None)
        return data

    def get_file_url(self, obj):
        if not obj.file:
            return None
        request = self.context.get('request')
        path = f'/api/chats/messages/{obj.id}/file/'
        return request.build_absolute_uri(path) if request else path

    def get_reply_to_data(self, obj):
        parent = obj.reply_to
        if not parent:
            return None
        return {
            'id': parent.id,
            'content': '' if parent.is_deleted else parent.content[:300],
            'message_type': parent.message_type,
            'is_deleted': parent.is_deleted,
            'sender': parent.sender.username if parent.sender else None,
        }

    def get_read_by_count(self, obj):
        annotated = getattr(obj, 'read_count', None)
        return annotated if annotated is not None else obj.reads.count()

    def _reactions(self, obj):
        # Uses prefetch_related('reactions') when the queryset provides it.
        return list(obj.reactions.all())

    def get_reactions(self, obj):
        return reaction_summary(self._reactions(obj))

    def get_my_reaction(self, obj):
        request = self.context.get('request')
        if not request:
            return None
        return next((r.reaction for r in self._reactions(obj) if r.user_id == request.user.id), None)


def reaction_summary(reactions):
    counts = Counter(r.reaction for r in reactions)
    order = [key for key, _ in MessageReaction.REACTION_CHOICES]
    return [{'reaction': key, 'count': counts[key]} for key in order if counts[key]]


class ChatMemberSerializer(serializers.ModelSerializer):
    user = ChatUserSerializer(read_only=True)

    class Meta:
        model = ChatMember
        fields = ['id', 'user', 'role', 'last_read_at', 'joined_at']


class ChatRoomSerializer(serializers.ModelSerializer):
    members = ChatMemberSerializer(source='chatmember_set', many=True, read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    my_role = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = [
            'id', 'room_type', 'name', 'avatar',
            'members', 'my_role', 'last_message', 'unread_count',
            'created_at', 'updated_at',
        ]

    def get_last_message(self, obj):
        prefetched = self.context.get('last_messages')
        if prefetched is not None:
            msg = prefetched.get(getattr(obj, '_last_message_id', None))
        else:
            msg = obj.messages.filter(is_deleted=False).select_related('sender').order_by('-created_at').first()
        return LastMessageSerializer(msg, context=self.context).data if msg else None

    def get_unread_count(self, obj):
        annotated = getattr(obj, '_unread', None)
        if annotated is not None:
            return annotated
        request = self.context.get('request')
        if not request:
            return 0
        member = obj.chatmember_set.filter(user=request.user).first()
        msgs = obj.messages.filter(is_deleted=False).exclude(sender_id=request.user.id)
        if member and member.last_read_at:
            msgs = msgs.filter(created_at__gt=member.last_read_at)
        return msgs.count()

    def get_my_role(self, obj):
        request = self.context.get('request')
        if not request:
            return None
        return next((m.role for m in obj.chatmember_set.all() if m.user_id == request.user.id), None)


class LastMessageSerializer(serializers.ModelSerializer):
    """Room-list preview: no reactions, reads or reply data."""

    sender = ChatUserSerializer(read_only=True)

    class Meta:
        model = Message
        fields = ['id', 'sender', 'content', 'message_type', 'created_at']
        read_only_fields = fields
