from rest_framework import serializers
from .models import ChatRoom, ChatMember, Message
from users.serializers import UserSerializer


class MessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    reply_to_data = serializers.SerializerMethodField()
    read_by_count = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    content = serializers.CharField(max_length=5000, allow_blank=True, required=False)

    class Meta:
        model = Message
        fields = [
            'id', 'room', 'sender', 'content', 'message_type',
            'file', 'file_url', 'reply_to', 'reply_to_data',
            'is_edited', 'is_deleted', 'read_by_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['sender', 'is_edited', 'is_deleted', 'created_at', 'updated_at']
        # Attachments are private: clients get an authenticated URL, never the storage path.
        extra_kwargs = {'file': {'write_only': True}}

    def validate(self, attrs):
        if self.instance is not None:
            # Edits may only change the text.
            attrs = {k: v for k, v in attrs.items() if k == 'content'}
        return attrs

    def get_file_url(self, obj):
        if not obj.file:
            return None
        request = self.context.get('request')
        path = f'/api/chats/messages/{obj.id}/file/'
        return request.build_absolute_uri(path) if request else path

    def get_reply_to_data(self, obj):
        if obj.reply_to:
            return {
                'id': obj.reply_to.id,
                'content': obj.reply_to.content,
                'sender': obj.reply_to.sender.username if obj.reply_to.sender else None,
            }
        return None

    def get_read_by_count(self, obj):
        return obj.reads.count()


class ChatMemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = ChatMember
        fields = ['id', 'user', 'role', 'last_read_at', 'joined_at']


class ChatRoomSerializer(serializers.ModelSerializer):
    members = ChatMemberSerializer(source='chatmember_set', many=True, read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = [
            'id', 'room_type', 'name', 'avatar',
            'members', 'last_message', 'unread_count',
            'created_at', 'updated_at',
        ]

    def get_last_message(self, obj):
        msg = obj.messages.filter(is_deleted=False).order_by('-created_at').first()
        return MessageSerializer(msg, context=self.context).data if msg else None

    def get_unread_count(self, obj):
        request = self.context.get('request')
        if not request:
            return 0
        member = obj.chatmember_set.filter(user=request.user).first()
        if not member or not member.last_read_at:
            return obj.messages.count()
        return obj.messages.filter(created_at__gt=member.last_read_at).count()
