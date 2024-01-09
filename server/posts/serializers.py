from rest_framework import serializers
from .models import Post, Like, Comment, PostMedia, PostTag
from users.serializers import UserSerializer


class PostTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostTag
        fields = ['name']


class PostMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostMedia
        fields = ['id', 'file', 'media_type', 'order']


class CommentSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    replies = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ['id', 'post', 'author', 'content', 'parent', 'likes_count', 'replies', 'created_at']
        read_only_fields = ['post', 'author', 'likes_count', 'created_at']
        extra_kwargs = {
            'parent': {'required': False, 'allow_null': True},
        }

    def get_replies(self, obj):
        if obj.parent is None:
            return CommentSerializer(obj.replies.all()[:5], many=True, context=self.context).data
        return []


class PostSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    tags = PostTagSerializer(many=True, read_only=True)
    media = PostMediaSerializer(many=True, read_only=True)
    my_reaction = serializers.SerializerMethodField()
    shared_post_data = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            'id', 'author', 'content', 'post_type', 'privacy',
            'image', 'video', 'link_url', 'link_title', 'link_description', 'link_image',
            'group', 'page',
            'likes_count', 'comments_count', 'shares_count',
            'shared_post', 'shared_post_data',
            'is_edited', 'tags', 'media', 'my_reaction',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['author', 'likes_count', 'comments_count', 'shares_count', 'is_edited']

    def get_my_reaction(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            like = Like.objects.filter(user=request.user, post=obj).first()
            return like.reaction if like else None
        return None

    def get_shared_post_data(self, obj):
        if obj.shared_post:
            return PostSerializer(obj.shared_post, context=self.context).data
        return None
