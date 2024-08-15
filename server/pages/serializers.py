from rest_framework import serializers
from .models import Page, PagePost

class PageSerializer(serializers.Serializer):
    uid = serializers.CharField(read_only=True)
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)
    created = serializers.DateTimeField(read_only=True)
    updated = serializers.DateTimeField(read_only=True)
    creator_id = serializers.SerializerMethodField()
    followers_count = serializers.SerializerMethodField()
    likes_count = serializers.SerializerMethodField()

    def get_creator_id(self, obj):
        return obj.creator.single().uid if obj.creator else None

    def get_followers_count(self, obj):
        return len(obj.followers.all())

    def get_likes_count(self, obj):
        return len(obj.likes.all())

    def create(self, validated_data):
        page = Page(**validated_data)
        page.save()
        return page

class PagePostSerializer(serializers.Serializer):
    uid = serializers.CharField(read_only=True)
    page_id = serializers.SerializerMethodField()
    post_id = serializers.SerializerMethodField()
    created = serializers.DateTimeField(read_only=True)

    def get_page_id(self, obj):
        return obj.page.single().uid if obj.page else None

    def get_post_id(self, obj):
        return obj.post.single().uid if obj.post else None

    def create(self, validated_data):
        page_post = PagePostNode(**validated_data)
        page_post.save()
        return page_post
