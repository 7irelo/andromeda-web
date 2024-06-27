from rest_framework import serializers
from .models import Chat, Message

class ChatSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chat
        fields = ['id', 'text', 'participants', 'updated', 'created']


    def create(self, validated_data):
        # Create a new instance of Chat with the validated data
        instance = Chat.objects.create(**validated_data)
        return instance

class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ['id', 'user', 'chat', 'text', 'updated', 'created']

    def create(self, validated_data):
        # Create a new instance of Message with the validated data
        instance = Message.objects.create(**validated_data)
        return instance
