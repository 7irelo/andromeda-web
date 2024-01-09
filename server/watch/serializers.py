from rest_framework import serializers
from .models import Video, VideoComment
from users.serializers import UserSerializer


class VideoCommentSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)

    class Meta:
        model = VideoComment
        fields = ['id', 'video', 'author', 'content', 'parent', 'likes_count', 'created_at']
        read_only_fields = ['video', 'author', 'likes_count']
        extra_kwargs = {
            'parent': {'required': False, 'allow_null': True},
        }


class VideoSerializer(serializers.ModelSerializer):
    uploader = UserSerializer(read_only=True)
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = Video
        fields = [
            'id', 'uploader', 'title', 'description',
            'video_file', 'thumbnail', 'duration', 'status',
            'views_count', 'likes_count', 'comments_count',
            'is_public', 'tags', 'is_liked', 'created_at',
        ]
        read_only_fields = ['uploader', 'views_count', 'likes_count', 'comments_count', 'status']

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.likes.filter(user=request.user).exists()
        return False
