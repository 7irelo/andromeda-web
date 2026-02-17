from rest_framework import serializers
from .models import Notification
from users.serializers import UserSerializer


class NotificationSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)

    class Meta:
        model = Notification
        fields = ['id', 'sender', 'notification_type', 'title', 'body', 'is_read', 'extra', 'created_at']
        read_only_fields = ['sender', 'notification_type', 'title', 'body', 'extra', 'created_at']
