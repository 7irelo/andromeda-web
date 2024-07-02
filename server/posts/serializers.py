from rest_framework import serializers
from .models import Post, Comment
from users.serializers import SimpleUserSerializer

class PostSerializer(serializers.ModelSerializer):
    creator = SimpleUserSerializer(read_only=True)
    participants = SimpleUserSerializer(read_only=True, many=True)
    likes_count = serializers.IntegerField(source='likes.count', read_only=True)
    comments_count = serializers.IntegerField(source='comment_set.count', read_only=True)

    class Meta:
        model = Post
        fields = ['id', 'creator', 'text', 'participants', 'likes_count', 'comments_count', 'updated', 'created']
        read_only_fields = ['id', 'creator', 'updated', 'created', 'likes_count', 'comments_count']

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user if request else None
        return Post.objects.create(creator=user, **validated_data)

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
