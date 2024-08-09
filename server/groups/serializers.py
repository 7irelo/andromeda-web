from rest_framework import serializers
from .models import Group, GroupMessage
from users.serializers import SimpleUserSerializer

class GroupSerializer(serializers.ModelSerializer):
    members = SimpleUserSerializer(many=True, read_only=True)

    class Meta:
        model = Group
        fields = ['uid', 'name', 'description', 'members', 'created', 'updated']

    def create(self, validated_data):
        instance = Group(**validated_data)
        instance.save()
        return instance

class GroupMessageSerializer(serializers.ModelSerializer):
    sender = SimpleUserSerializer(read_only=True)

    class Meta:
        model = GroupMessage
        fields = ['uid', 'text', 'sender', 'group', 'created', 'updated']

    def create(self, validated_data):
        instance = GroupMessage(**validated_data)
        instance.save()
        return instance
