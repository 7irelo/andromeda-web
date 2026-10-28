from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers
from core.validators import sanitize_image
from .models import Group, GroupBan, GroupInvite, GroupJoinRequest, GroupMember, GroupRule
from users.serializers import UserSerializer

MAX_RULES = 20
MAX_INVITE_DAYS = 30
MAX_INVITE_USES = 1000


class GroupMemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = GroupMember
        fields = ['id', 'user', 'role', 'joined_at']


class GroupSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    is_member = serializers.SerializerMethodField()
    my_role = serializers.SerializerMethodField()
    is_banned = serializers.SerializerMethodField()
    has_requested = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = [
            'id', 'name', 'description', 'cover_photo', 'avatar',
            'privacy', 'created_by', 'members_count',
            'is_member', 'my_role', 'is_banned', 'has_requested', 'created_at',
        ]
        read_only_fields = ['created_by', 'members_count']

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('A group needs a name.')
        return value

    def validate_description(self, value):
        if len(value) > 5000:
            raise serializers.ValidationError('Keep the description under 5000 characters.')
        return value

    def validate_avatar(self, value):
        return sanitize_image(value) if value else value

    def validate_cover_photo(self, value):
        return sanitize_image(value) if value else value

    def _user(self):
        request = self.context.get('request')
        return request.user if request and request.user.is_authenticated else None

    def get_is_member(self, obj):
        user = self._user()
        return bool(user) and obj.memberships.filter(user=user).exists()

    def get_my_role(self, obj):
        user = self._user()
        if user:
            m = obj.memberships.filter(user=user).first()
            return m.role if m else None
        return None

    def get_is_banned(self, obj):
        user = self._user()
        return bool(user) and obj.bans.filter(user=user).exists()

    def get_has_requested(self, obj):
        user = self._user()
        return bool(user) and obj.join_requests.filter(user=user, status=GroupJoinRequest.STATUS_PENDING).exists()


class GroupJoinRequestSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = GroupJoinRequest
        fields = ['id', 'user', 'status', 'created_at']
        read_only_fields = fields


class GroupBanSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = GroupBan
        fields = ['id', 'user', 'reason', 'created_at']
        read_only_fields = fields


class GroupRuleSerializer(serializers.ModelSerializer):
    title = serializers.CharField(max_length=120)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True, default='')

    class Meta:
        model = GroupRule
        fields = ['id', 'position', 'title', 'description']
        read_only_fields = ['id', 'position']


class GroupRulesUpdateSerializer(serializers.Serializer):
    """The whole ordered list is replaced at once; list order is rule order."""

    rules = GroupRuleSerializer(many=True)

    def validate_rules(self, value):
        if len(value) > MAX_RULES:
            raise serializers.ValidationError(f'A group can have at most {MAX_RULES} rules.')
        return value


class GroupInviteSerializer(serializers.ModelSerializer):
    """Never includes the token; it is only returned once, from the create call."""

    created_by = UserSerializer(read_only=True)
    is_usable = serializers.BooleanField(read_only=True)

    class Meta:
        model = GroupInvite
        fields = ['id', 'created_by', 'expires_at', 'max_uses', 'uses_count', 'revoked_at', 'is_usable', 'created_at']
        read_only_fields = fields


class GroupInviteCreateSerializer(serializers.Serializer):
    expires_in_hours = serializers.IntegerField(min_value=1, max_value=MAX_INVITE_DAYS * 24, default=7 * 24)
    max_uses = serializers.IntegerField(min_value=1, max_value=MAX_INVITE_USES, required=False, allow_null=True)

    def expires_at(self):
        return timezone.now() + timedelta(hours=self.validated_data['expires_in_hours'])


class GroupInvitePreviewSerializer(serializers.ModelSerializer):
    """What an invite holder may see before joining: the group card and its rules, no content."""

    rules = GroupRuleSerializer(many=True, read_only=True)

    class Meta:
        model = Group
        fields = ['id', 'name', 'description', 'cover_photo', 'avatar', 'privacy', 'members_count', 'rules']
        read_only_fields = fields
