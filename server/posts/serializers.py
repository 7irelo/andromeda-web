from django.db.models import Q
from rest_framework import serializers

from core import visibility
from core.permissions import is_page_admin
from core.validators import sanitize_image, validate_video
from users.serializers import UserSerializer
from .models import Post, Like, Comment, PostMedia, PostTag


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
    content = serializers.CharField(max_length=5000)

    class Meta:
        model = Comment
        fields = ['id', 'post', 'author', 'content', 'parent', 'likes_count', 'replies', 'created_at']
        read_only_fields = ['post', 'author', 'likes_count', 'created_at']
        extra_kwargs = {
            'parent': {'required': False, 'allow_null': True},
        }

    def validate(self, attrs):
        post = self.context.get('post')
        parent = attrs.get('parent')
        if parent is not None and post is not None and parent.post_id != post.id:
            raise serializers.ValidationError({'parent': 'Replies must belong to the same post.'})
        if self.instance is not None:
            attrs = {k: v for k, v in attrs.items() if k == 'content'}
        return attrs

    def get_replies(self, obj):
        if obj.parent is None:
            request = self.context.get('request')
            replies = obj.replies.all()
            if request:
                replies = replies.exclude(author_id__in=visibility.blocked_ids(request.user)).exclude(
                    Q(moderation_status='removed') & ~Q(author=request.user))
            return CommentSerializer(replies[:5], many=True, context=self.context).data
        return []


class PostSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    tags = PostTagSerializer(many=True, read_only=True)
    media = PostMediaSerializer(many=True, read_only=True)
    my_reaction = serializers.SerializerMethodField()
    shared_post_data = serializers.SerializerMethodField()
    content = serializers.CharField(max_length=10000, allow_blank=True, required=False)

    class Meta:
        model = Post
        fields = [
            'id', 'author', 'content', 'post_type', 'privacy',
            'image', 'video', 'link_url', 'link_title', 'link_description', 'link_image',
            'group', 'page',
            'likes_count', 'comments_count', 'shares_count',
            'shared_post', 'shared_post_data',
            'is_edited', 'tags', 'media', 'my_reaction', 'moderation_status',
            'created_at', 'updated_at',
        ]
        # Shares go through the share action, which checks the original's visibility.
        read_only_fields = ['author', 'likes_count', 'comments_count', 'shares_count',
                            'is_edited', 'shared_post', 'moderation_status']

    def _user(self):
        return self.context['request'].user

    def validate_image(self, value):
        return sanitize_image(value) if value else value

    def validate_video(self, value):
        return validate_video(value) if value else value

    def validate_link_url(self, value):
        if value and not value.lower().startswith(('http://', 'https://')):
            raise serializers.ValidationError('Only http(s) links are allowed.')
        return value

    validate_link_image = validate_link_url

    def validate_group(self, group):
        if group is None:
            return group
        if self.instance is not None and self.instance.group_id != group.id:
            raise serializers.ValidationError('A post cannot be moved to another group.')
        if not group.memberships.filter(user=self._user()).exists():
            raise serializers.ValidationError('Join this group before posting in it.')
        return group

    def validate_page(self, page):
        if page is None:
            return page
        if self.instance is not None and self.instance.page_id != page.id:
            raise serializers.ValidationError('A post cannot be moved to another page.')
        if not is_page_admin(self._user(), page, roles=('admin', 'editor')):
            raise serializers.ValidationError('Only page admins and editors can post as this page.')
        return page

    def get_my_reaction(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            like = Like.objects.filter(user=request.user, post=obj).first()
            return like.reaction if like else None
        return None

    def get_shared_post_data(self, obj):
        if not obj.shared_post:
            return None
        request = self.context.get('request')
        if request and not visibility.can_view_post(request.user, obj.shared_post):
            return {'id': None, 'unavailable': True}
        return PostSerializer(obj.shared_post, context=self.context).data
