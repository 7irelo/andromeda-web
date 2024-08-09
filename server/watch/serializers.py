from rest_framework import serializers
from .models import Video, VideoComment

class VideoSerializer(serializers.Serializer):
    uid = serializers.CharField(read_only=True)
    title = serializers.CharField(max_length=255)
    description = serializers.CharField()
    url = serializers.CharField()
    tags = serializers.CharField()
    updated = serializers.DateTimeField()
    created = serializers.DateTimeField()

    def create(self, validated_data):
        return Video(**validated_data).save()

    def update(self, instance, validated_data):
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        return instance

class VideoCommentSerializer(serializers.Serializer):
    uid = serializers.CharField(read_only=True)
    text = serializers.CharField()
    updated = serializers.DateTimeField()
    created = serializers.DateTimeField()

    def create(self, validated_data):
        return VideoComment(**validated_data).save()

    def update(self, instance, validated_data):
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        return instance
