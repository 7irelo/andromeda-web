from rest_framework import serializers
from .models import Chat, Message
from users.serializers import SimpleUserSerializer

class ChatSerializer(serializers.ModelSerializer):
    participants = SimpleUserSerializer(many=True, read_only=True)

    class Meta:
        model = Chat
        fields = ['uid', 'text', 'participants', 'updated', 'created']

    def create(self, validated_data):
        instance = Chat(**validated_data)
        instance.save()
        return instance

class MessageSerializer(serializers.ModelSerializer):
    user = SimpleUserSerializer(read_only=True)

    class Meta:
        model = Message
        fields = ['uid', 'user', 'chat', 'text', 'updated', 'created']

    def create(self, validated_data):
        instance = Message(**validated_data)
        instance.save()
        return instance
