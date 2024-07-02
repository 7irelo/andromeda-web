from rest_framework import serializers
from .models import Post, Comment, Tag
from users.serializers import SimpleUserSerializer

class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name']

class PostSerializer(serializers.ModelSerializer):
    creator = SimpleUserSerializer(read_only=True)
    participants = SimpleUserSerializer(read_only=True, many=True)
    likes_count = serializers.IntegerField(source='likes.count', read_only=True)
    comments_count = serializers.IntegerField(source='comment_set.count', read_only=True)
    tags = TagSerializer(many=True, read_only=True)

    class Meta:
        model = Post
        fields = ['id', 'creator', 'content', 'participants', 'likes_count', 'comments_count', 'updated', 'created', 'tags']
        read_only_fields = ['id', 'creator', 'updated', 'created', 'likes_count', 'comments_count', 'tags']

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user if request else None
        tags_data = validated_data.pop('tags', [])
        post = Post.objects.create(creator=user, **validated_data)
        post.tags.set(tags_data)
        return post

class CommentSerializer(serializers.ModelSerializer):
    user = SimpleUserSerializer(read_only=True)

    class Meta:
        model = Comment
        fields = ['id', 'user', 'post', 'text', 'updated', 'created']
        read_only_fields = ['id', 'user', 'updated', 'created']

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user if request else None
        return Comment.objects.create(user=user, **validated_data)
