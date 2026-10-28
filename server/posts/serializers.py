from django.db.models import Q
from rest_framework import serializers

from core import visibility
from core.permissions import is_page_admin
from core.validators import sanitize_image, validate_video
from imaging import variants
from users.serializers import BASIC_FIELDS, UserSerializer
from .models import Post, Like, Comment, PostMedia, PostRevision, PostTag, SavedPost

MAX_IMAGES = 10
MAX_REPLIES = 50
_UNSET = object()


class AuthorSerializer(UserSerializer):
    """
    Post and comment authors: only the basic fields, which anyone who can see
    the content may see. Skips the per-user relationship lookups of
    ``UserSerializer`` so lists don't do several queries per row.
    """

    class Meta(UserSerializer.Meta):
        fields = BASIC_FIELDS
        read_only_fields = fields

    def to_representation(self, obj):
        return serializers.ModelSerializer.to_representation(self, obj)


def viewer_state(user, posts):
    """
    Per-viewer flags for a page of posts (and the posts they share), fetched in
    three queries instead of several per post. Passed to serializers as context.
    """
    posts = list(posts)
    ids = {p.id for p in posts} | {p.shared_post_id for p in posts if p.shared_post_id}
    shared = {p.shared_post_id for p in posts if p.shared_post_id}
    if not user.is_authenticated or not ids:
        return {'reactions': {}, 'saved': set(), 'visible_shared': set()}
    return {
        'reactions': dict(Like.objects.filter(user=user, post_id__in=ids).values_list('post_id', 'reaction')),
        'saved': set(SavedPost.objects.filter(user=user, post_id__in=ids).values_list('post_id', flat=True)),
        'visible_shared': set(visibility.visible_posts(user).filter(id__in=shared).values_list('id', flat=True)),
    }


class PostTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostTag
        fields = ['name']


class PostMediaSerializer(serializers.ModelSerializer):
    # {'thumb', 'medium', 'srcset'}: WebP variants for <img srcset>, or null.
    variants = serializers.SerializerMethodField()

    class Meta:
        model = PostMedia
        fields = ['id', 'file', 'variants', 'media_type', 'order']

    def get_variants(self, obj):
        if obj.media_type != 'image':
            return None
        return variants.urls(obj.file, variants.POST_WIDTHS, self.context.get('request'))


class PostRevisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostRevision
        fields = ['id', 'content', 'created_at']


class CommentSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    replies = serializers.SerializerMethodField()
    liked = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    content = serializers.CharField(max_length=5000)

    class Meta:
        model = Comment
        fields = ['id', 'post', 'author', 'content', 'parent', 'likes_count', 'liked', 'is_edited',
                  'can_delete', 'replies', 'created_at', 'updated_at']
        read_only_fields = ['post', 'author', 'likes_count', 'is_edited', 'created_at', 'updated_at']
        extra_kwargs = {
            'parent': {'required': False, 'allow_null': True},
        }

    def _user(self):
        request = self.context.get('request')
        return request.user if request else None

    def validate(self, attrs):
        if self.instance is not None:
            # Edits change the text only, never the post or the thread.
            return {k: v for k, v in attrs.items() if k == 'content'}
        post = self.context.get('post')
        parent = attrs.get('parent')
        if parent is not None:
            if post is not None and parent.post_id != post.id:
                raise serializers.ValidationError({'parent': 'Replies must belong to the same post.'})
            user = self._user()
            hidden = parent.moderation_status == 'removed' and parent.author_id != getattr(user, 'id', None)
            if user is not None and (hidden or parent.author_id in visibility.blocked_ids(user)):
                raise serializers.ValidationError({'parent': 'That comment is not available.'})
            # One level of nesting: a reply to a reply joins the top-level thread.
            if parent.parent_id is not None:
                attrs['parent'] = parent.parent
        return attrs

    def get_replies(self, obj):
        if obj.parent_id is not None:
            return []
        replies = getattr(obj, 'visible_replies', _UNSET)
        if replies is _UNSET:
            replies = obj.replies.select_related('author')
            user = self._user()
            if user is not None:
                replies = visible_comments(user, replies)
            replies = replies[:MAX_REPLIES]
        return CommentSerializer(replies, many=True, context=self.context).data

    def get_liked(self, obj):
        liked = self.context.get('liked_comments')
        if liked is not None:
            return obj.id in liked
        user = self._user()
        return bool(user and user.is_authenticated and obj.likes.filter(user=user).exists())

    def get_can_delete(self, obj):
        user = self._user()
        if user is None or not user.is_authenticated:
            return False
        if obj.author_id == user.id:
            return True
        moderates = self.context.get('moderates_post')
        if moderates is None:
            moderates = can_moderate_comments(user, obj.post)
        return moderates


def visible_comments(user, qs):
    """Hide comments by blocked users (either direction) and removed comments, except from their author."""
    return qs.exclude(author_id__in=visibility.blocked_ids(user)).exclude(
        Q(moderation_status='removed') & ~Q(author=user))


def can_moderate_comments(user, post):
    """The post's author, page admins for page posts, and group admins/moderators may delete any comment."""
    if post.author_id == user.id:
        return True
    if post.page_id and is_page_admin(user, post.page):
        return True
    if post.group_id:
        return post.group.memberships.filter(user=user, role__in=('admin', 'moderator')).exists()
    return False


class PostSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    tags = PostTagSerializer(many=True, read_only=True)
    media = PostMediaSerializer(many=True, read_only=True)
    images = serializers.ListField(
        child=serializers.FileField(), write_only=True, required=False, max_length=MAX_IMAGES,
        help_text=f'Up to {MAX_IMAGES} images, in display order.',
    )
    media_order = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False, max_length=MAX_IMAGES,
        help_text='On edit: the ids of the media to keep, in display order. Others are removed.',
    )
    image_variants = serializers.SerializerMethodField()
    my_reaction = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
    reason = serializers.SerializerMethodField()
    group_data = serializers.SerializerMethodField()
    page_data = serializers.SerializerMethodField()
    shared_post_data = serializers.SerializerMethodField()
    content = serializers.CharField(max_length=10000, allow_blank=True, required=False)

    class Meta:
        model = Post
        fields = [
            'id', 'author', 'content', 'post_type', 'privacy',
            'image', 'image_variants', 'video', 'link_url', 'link_title', 'link_description', 'link_image',
            'group', 'page', 'group_data', 'page_data',
            'likes_count', 'comments_count', 'shares_count',
            'shared_post', 'shared_post_data',
            'is_edited', 'tags', 'media', 'images', 'media_order',
            'my_reaction', 'is_saved', 'reason', 'moderation_status',
            'created_at', 'updated_at',
        ]
        # Shares go through the share action, which checks the original's visibility.
        read_only_fields = ['author', 'likes_count', 'comments_count', 'shares_count',
                            'is_edited', 'shared_post', 'moderation_status']

    def _user(self):
        return self.context['request'].user

    def _state(self, key):
        state = self.context.get('viewer_state')
        return state[key] if state is not None else None

    def validate_image(self, value):
        return sanitize_image(value) if value else value

    def validate_images(self, files):
        if self.instance is not None and len(files) + self.instance.media.count() > MAX_IMAGES:
            raise serializers.ValidationError(f'A post can have at most {MAX_IMAGES} images.')
        return [sanitize_image(f) for f in files]

    def validate_media_order(self, ids):
        if self.instance is None:
            raise serializers.ValidationError('Only used when editing a post.')
        if len(set(ids)) != len(ids):
            raise serializers.ValidationError('Duplicate media ids.')
        owned = set(self.instance.media.values_list('id', flat=True))
        if not set(ids) <= owned:
            raise serializers.ValidationError('Unknown media for this post.')
        return ids

    def validate_video(self, value):
        return validate_video(value) if value else value

    def validate_link_url(self, value):
        if value and not value.lower().startswith(('http://', 'https://')):
            raise serializers.ValidationError('Only http(s) links are allowed.')
        return value

    validate_link_image = validate_link_url

    def validate_group(self, group):
        if group is None:
            if self.instance is not None and self.instance.group_id is not None:
                raise serializers.ValidationError('A post cannot be moved out of its group.')
            return group
        if self.instance is not None and self.instance.group_id != group.id:
            raise serializers.ValidationError('A post cannot be moved to another group.')
        if not group.memberships.filter(user=self._user()).exists():
            raise serializers.ValidationError('Join this group before posting in it.')
        return group

    def validate_page(self, page):
        if page is None:
            if self.instance is not None and self.instance.page_id is not None:
                raise serializers.ValidationError('A post cannot be moved off its page.')
            return page
        if self.instance is not None and self.instance.page_id != page.id:
            raise serializers.ValidationError('A post cannot be moved to another page.')
        if not is_page_admin(self._user(), page, roles=('admin', 'editor')):
            raise serializers.ValidationError('Only page admins and editors can post as this page.')
        return page

    def validate(self, attrs):
        if attrs.get('images') and (attrs.get('video') or attrs.get('image')):
            raise serializers.ValidationError({'images': 'Post either several images or one video, not both.'})
        if attrs.get('images'):
            attrs['post_type'] = Post.TYPE_IMAGE
        return attrs

    def create(self, validated_data):
        images = validated_data.pop('images', [])
        validated_data.pop('media_order', None)
        post = super().create(validated_data)
        _add_images(post, images, start=0)
        return post

    def update(self, instance, validated_data):
        images = validated_data.pop('images', [])
        order = validated_data.pop('media_order', None)
        post = super().update(instance, validated_data)
        if order is not None:
            post.media.exclude(id__in=order).delete()
            for position, media_id in enumerate(order):
                PostMedia.objects.filter(post=post, id=media_id).update(order=position)
        _add_images(post, images, start=post.media.count())
        return post

    def get_image_variants(self, obj):
        return variants.urls(obj.image, variants.POST_WIDTHS, self.context.get('request'))

    def get_my_reaction(self, obj):
        reactions = self._state('reactions')
        if reactions is not None:
            return reactions.get(obj.id)
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            like = Like.objects.filter(user=request.user, post=obj).first()
            return like.reaction if like else None
        return None

    def get_is_saved(self, obj):
        saved = self._state('saved')
        if saved is not None:
            return obj.id in saved
        request = self.context.get('request')
        return bool(request and request.user.is_authenticated
                    and SavedPost.objects.filter(user=request.user, post=obj).exists())

    def get_reason(self, obj):
        return self.context.get('reasons', {}).get(obj.id)

    def get_group_data(self, obj):
        if not obj.group_id:
            return None
        return {'id': obj.group.id, 'name': obj.group.name}

    def get_page_data(self, obj):
        if not obj.page_id:
            return None
        page = obj.page
        request = self.context.get('request')
        avatar = request.build_absolute_uri(page.avatar.url) if page.avatar and request else None
        return {'id': page.id, 'name': page.name, 'username': page.username, 'avatar_url': avatar}

    def get_shared_post_data(self, obj):
        if not obj.shared_post:
            return None
        visible = self._state('visible_shared')
        request = self.context.get('request')
        if visible is not None:
            allowed = obj.shared_post_id in visible
        else:
            allowed = not request or visibility.can_view_post(request.user, obj.shared_post)
        if not allowed:
            return {'id': None, 'unavailable': True}
        context = {**self.context, 'reasons': {}}
        return PostSerializer(obj.shared_post, context=context).data


def _add_images(post, files, start):
    # Saved one by one so each file goes through the field's storage and RandomFilename.
    for i, f in enumerate(files):
        PostMedia.objects.create(post=post, file=f, media_type='image', order=start + i)
