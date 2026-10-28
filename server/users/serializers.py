from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from core import viewer_cache, visibility
from core.validators import sanitize_image
from imaging import variants
from .models import User, FriendRequest

# Visible to anyone who can see the user at all (search results, post authors).
BASIC_FIELDS = ['id', 'username', 'first_name', 'last_name', 'full_name', 'avatar_url', 'avatar_variants',
                'is_verified']
# Visible when the viewer passes the user's profile-privacy setting.
PROFILE_FIELDS = BASIC_FIELDS + [
    'bio', 'cover_photo_url', 'location', 'website', 'friends_count', 'posts_count', 'created_at',
]
RELATIONSHIP_FIELDS = ['is_friend', 'friend_request_sent', 'friend_request_received', 'is_blocked']
# Only ever returned to the account owner.
PRIVATE_FIELDS = [
    'email', 'birth_date', 'avatar', 'cover_photo',
    'privacy_profile', 'privacy_messages', 'privacy_friend_requests',
    'privacy_friends_list', 'default_post_privacy', 'show_online_status', 'searchable',
    'email_verified', 'ai_opt_out', 'is_staff',
]


def _absolute(request, f):
    if f and request:
        return request.build_absolute_uri(f.url)
    return None


class UserSerializer(serializers.ModelSerializer):
    """
    Public view of a user. Fields are trimmed to what the viewer is entitled
    to see: email, birth date and privacy settings are never exposed to other
    users, and profile details respect ``privacy_profile``.
    """

    avatar_url = serializers.SerializerMethodField()
    # {'thumb', 'medium', 'srcset'}: WebP variants for <img srcset>, or null.
    avatar_variants = serializers.SerializerMethodField()
    cover_photo_url = serializers.SerializerMethodField()
    is_friend = serializers.SerializerMethodField()
    friend_request_sent = serializers.SerializerMethodField()
    friend_request_received = serializers.SerializerMethodField()
    is_blocked = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = PROFILE_FIELDS + RELATIONSHIP_FIELDS
        read_only_fields = fields

    def _viewer(self):
        request = self.context.get('request')
        return request.user if request and request.user.is_authenticated else None

    def to_representation(self, obj):
        data = super().to_representation(obj)
        viewer = self._viewer()
        if viewer is None or (viewer.id != obj.id and not visibility.can_view_profile(
                viewer, obj, viewer_cache.relations(self))):
            allowed = set(BASIC_FIELDS + RELATIONSHIP_FIELDS)
            data = {k: v for k, v in data.items() if k in allowed}
        return data

    def get_avatar_url(self, obj):
        return _absolute(self.context.get('request'), obj.avatar)

    def get_avatar_variants(self, obj):
        return variants.urls(obj.avatar, variants.AVATAR_WIDTHS, self.context.get('request'))

    def get_cover_photo_url(self, obj):
        return _absolute(self.context.get('request'), obj.cover_photo)

    # Relationship flags come from the viewer's relations, loaded once per response
    # (core.viewer_cache), not from a query per user.

    def get_is_friend(self, obj):
        viewer = self._viewer()
        return bool(viewer and viewer.id != obj.id and obj.id in viewer_cache.relations(self).friends)

    def get_friend_request_sent(self, obj):
        viewer = self._viewer()
        return bool(viewer and viewer.id != obj.id and obj.id in viewer_cache.relations(self).sent)

    def get_friend_request_received(self, obj):
        viewer = self._viewer()
        return bool(viewer and viewer.id != obj.id and obj.id in viewer_cache.relations(self).received)

    def get_is_blocked(self, obj):
        """True only when the viewer blocked this user (never reveals being blocked)."""
        viewer = self._viewer()
        return bool(viewer and obj.id in viewer_cache.relations(self).i_blocked)


class MeSerializer(UserSerializer):
    """The account owner's own view, including private fields and settings."""

    class Meta(UserSerializer.Meta):
        fields = PROFILE_FIELDS + PRIVATE_FIELDS
        # Username and email changes go through dedicated, re-authenticated flows.
        read_only_fields = ['id', 'username', 'email', 'full_name', 'is_verified', 'email_verified', 'is_staff',
                            'friends_count', 'posts_count', 'created_at']
        extra_kwargs = {'avatar': {'write_only': True}, 'cover_photo': {'write_only': True}}

    def to_representation(self, obj):
        return serializers.ModelSerializer.to_representation(self, obj)

    def validate_avatar(self, value):
        return sanitize_image(value) if value else value

    def validate_cover_photo(self, value):
        return sanitize_image(value) if value else value


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)
    accept_terms = serializers.BooleanField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password', 'password2', 'accept_terms']

    def validate_accept_terms(self, value):
        if value is not True:
            raise serializers.ValidationError('Please accept the terms and privacy policy to create an account.')
        return value

    def validate_email(self, value):
        normalised = value.strip().lower()
        if User.objects.filter(email__iexact=normalised).exists():
            raise serializers.ValidationError('An account with this email address already exists.')
        return normalised

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('This username is already taken.')
        return value

    def validate(self, attrs):
        attrs.pop('accept_terms', None)
        if attrs['password'] != attrs.pop('password2'):
            raise serializers.ValidationError({'password': 'Passwords do not match.'})
        validate_password(attrs['password'], User(username=attrs['username'], email=attrs['email']))
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class AndromedaTokenSerializer(TokenObtainPairSerializer):
    # Keep the access token free of PII: it's a bearer credential that ends up
    # in browser memory and, potentially, in logs.

    def validate(self, attrs):
        data = super().validate(attrs)
        from core.auth import account_block_reason
        reason = account_block_reason(self.user)
        # Pending deletion is cancelled by signing in (see LoginView); suspension isn't.
        if reason and self.user.deletion_scheduled_at is None:
            raise serializers.ValidationError({'detail': reason})
        return data


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        if not self.context['request'].user.check_password(value):
            raise serializers.ValidationError('Current password is incorrect.')
        return value

    def validate(self, attrs):
        validate_password(attrs['new_password'], self.context['request'].user)
        if attrs['new_password'] == attrs['current_password']:
            raise serializers.ValidationError({'new_password': 'Choose a different password.'})
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)


class ReauthSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)

    def validate_password(self, value):
        if not self.context['request'].user.check_password(value):
            raise serializers.ValidationError('Password is incorrect.')
        return value


class FriendRequestSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    receiver = UserSerializer(read_only=True)

    class Meta:
        model = FriendRequest
        fields = ['id', 'sender', 'receiver', 'status', 'created_at']
        read_only_fields = fields
