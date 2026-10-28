from rest_framework import serializers
from core import viewer_cache
from core.validators import sanitize_image, validate_video
from .access import asset_url
from .models import ChannelSubscription, Video, VideoComment, VideoLike, WatchProgress
from users.serializers import UserSerializer

MAX_TAGS = 10
MAX_TAG_CHARS = 30


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
    thumbnail_url = serializers.SerializerMethodField()
    sprite_url = serializers.SerializerMethodField()
    playback_url = serializers.SerializerMethodField()
    playback_type = serializers.SerializerMethodField()
    failure_reason = serializers.SerializerMethodField()

    class Meta:
        model = Video
        fields = [
            'id', 'uploader', 'title', 'description',
            'video_file', 'thumbnail', 'thumbnail_url', 'sprite_url', 'playback_url', 'playback_type',
            'duration', 'width', 'height', 'renditions', 'status', 'failure_reason', 'captions_status',
            'views_count', 'likes_count', 'comments_count',
            'is_public', 'tags', 'is_liked', 'created_at', 'updated_at',
        ]
        read_only_fields = ['uploader', 'views_count', 'likes_count', 'comments_count', 'status', 'duration',
                            'width', 'height', 'renditions', 'captions_status']
        # The original upload is never handed back: viewers get HLS renditions.
        extra_kwargs = {'video_file': {'write_only': True}, 'thumbnail': {'write_only': True, 'required': False}}

    def _user(self):
        request = self.context.get('request')
        return request.user if request else None

    def validate_video_file(self, value):
        return validate_video(value)

    def validate_thumbnail(self, value):
        return sanitize_image(value) if value else value

    def validate_tags(self, value):
        if not isinstance(value, list) or len(value) > MAX_TAGS:
            raise serializers.ValidationError(f'Use at most {MAX_TAGS} tags.')
        tags = []
        for tag in value:
            if not isinstance(tag, str) or not tag.strip() or len(tag.strip()) > MAX_TAG_CHARS:
                raise serializers.ValidationError(f'Tags must be text of at most {MAX_TAG_CHARS} characters.')
            tags.append(tag.strip())
        return tags

    def validate(self, attrs):
        if self.instance is not None:
            # Replacing media means a new upload, not an edit.
            for field in ('video_file', 'thumbnail'):
                if field in attrs:
                    raise serializers.ValidationError({field: 'This can only be set when uploading.'})
        elif 'video_file' not in attrs:
            raise serializers.ValidationError({'video_file': 'Choose a video to upload.'})
        return attrs

    def get_is_liked(self, obj):
        user = self._user()
        if user and user.is_authenticated:
            return obj.id in viewer_cache.memo(self, ('video_likes', user.id), lambda: set(
                VideoLike.objects.filter(user=user).values_list('video_id', flat=True)))
        return False

    def get_thumbnail_url(self, obj):
        return asset_url(obj, 'thumb.jpg', self._user())

    def get_sprite_url(self, obj):
        return asset_url(obj, 'sprite.jpg', self._user())

    def _legacy_file(self, obj):
        # Videos uploaded before the HLS pipeline: public originals, played directly.
        name = obj.video_file.name if obj.video_file else ''
        return obj.status == Video.STATUS_READY and not obj.asset_files and obj.is_public and \
            name.startswith('public/')

    def get_playback_url(self, obj):
        if obj.status != Video.STATUS_READY:
            return None
        if self._legacy_file(obj):
            return obj.video_file.url
        return asset_url(obj, 'master.m3u8', self._user())

    def get_playback_type(self, obj):
        return 'file' if self._legacy_file(obj) else 'hls'

    def get_failure_reason(self, obj):
        user = self._user()
        return obj.failure_reason if user and obj.uploader_id == user.id else ''


class VideoDetailSerializer(VideoSerializer):
    chapters = serializers.JSONField(read_only=True)
    has_captions = serializers.SerializerMethodField()
    has_transcript = serializers.SerializerMethodField()
    resume_position_s = serializers.SerializerMethodField()
    channel = serializers.SerializerMethodField()

    class Meta(VideoSerializer.Meta):
        fields = VideoSerializer.Meta.fields + [
            'chapters', 'has_captions', 'has_transcript', 'resume_position_s', 'channel', 'transcript_language',
        ]
        read_only_fields = VideoSerializer.Meta.read_only_fields + ['transcript_language']

    def get_has_captions(self, obj):
        return bool(obj.captions_vtt)

    def get_has_transcript(self, obj):
        return bool(obj.transcript)

    def get_resume_position_s(self, obj):
        user = self._user()
        if not user or not user.is_authenticated:
            return 0
        return WatchProgress.objects.filter(user=user, video=obj).values_list('position_s', flat=True).first() or 0

    def get_channel(self, obj):
        user = self._user()
        return {
            'subscribers_count': ChannelSubscription.objects.filter(channel_id=obj.uploader_id).count(),
            'is_subscribed': bool(user and user.is_authenticated and ChannelSubscription.objects.filter(
                channel_id=obj.uploader_id, subscriber=user).exists()),
        }


class WatchProgressSerializer(serializers.Serializer):
    position_s = serializers.FloatField(min_value=0, max_value=24 * 60 * 60)


class WatchHistorySerializer(serializers.ModelSerializer):
    video = VideoSerializer(read_only=True)

    class Meta:
        model = WatchProgress
        fields = ['video', 'position_s', 'updated_at']
        read_only_fields = fields
