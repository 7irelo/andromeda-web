from django.contrib.auth.password_validation import validate_password
from django.db.models import Q
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User, FriendRequest, Follow


class UserSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()
    cover_photo_url = serializers.SerializerMethodField()
    is_friend = serializers.SerializerMethodField()
    is_following = serializers.SerializerMethodField()
    friend_request_sent = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'full_name', 'bio', 'avatar_url', 'avatar', 'cover_photo_url', 'cover_photo',
            'location', 'website', 'birth_date', 'is_verified',
            'followers_count', 'following_count', 'friends_count', 'posts_count',
            'created_at', 'is_friend', 'is_following', 'friend_request_sent',
        ]
        read_only_fields = [
            'id', 'followers_count', 'following_count', 'friends_count',
            'posts_count', 'created_at', 'is_verified',
        ]
        extra_kwargs = {
            'avatar': {'write_only': True},
            'cover_photo': {'write_only': True},
        }

    def get_avatar_url(self, obj):
        request = self.context.get('request')
        if obj.avatar and request:
            return request.build_absolute_uri(obj.avatar.url)
        return None

    def get_cover_photo_url(self, obj):
        request = self.context.get('request')
        if obj.cover_photo and request:
            return request.build_absolute_uri(obj.cover_photo.url)
        return None

    def get_is_friend(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated and request.user != obj:
            return FriendRequest.objects.filter(
                status=FriendRequest.STATUS_ACCEPTED
            ).filter(
                Q(sender=request.user, receiver=obj) |
                Q(sender=obj, receiver=request.user)
            ).exists()
        return False

    def get_is_following(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return Follow.objects.filter(follower=request.user, following=obj).exists()
        return False

    def get_friend_request_sent(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated and request.user != obj:
            return FriendRequest.objects.filter(
                sender=request.user,
                receiver=obj,
                status=FriendRequest.STATUS_PENDING,
            ).exists()
        return False


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password', 'password2']

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
        if attrs['password'] != attrs.pop('password2'):
            raise serializers.ValidationError({'password': 'Passwords do not match.'})
        return attrs

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user


class AndromedaTokenSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['email'] = user.email
        token['is_verified'] = user.is_verified
        return token


class FriendRequestSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    receiver = UserSerializer(read_only=True)

    class Meta:
        model = FriendRequest
        fields = ['id', 'sender', 'receiver', 'status', 'created_at']
        read_only_fields = ['sender', 'status', 'created_at']


class FollowSerializer(serializers.ModelSerializer):
    follower = UserSerializer(read_only=True)
    following = UserSerializer(read_only=True)

    class Meta:
        model = Follow
        fields = ['id', 'follower', 'following', 'created_at']
        read_only_fields = ['follower', 'following', 'created_at']
