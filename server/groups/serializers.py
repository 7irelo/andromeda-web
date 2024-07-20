from rest_framework import serializers
from .models import Group, GroupMember
from users.serializers import UserSerializer


class GroupMemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = GroupMember
        fields = ['id', 'user', 'role', 'joined_at']


class GroupSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    is_member = serializers.SerializerMethodField()
    my_role = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = [
            'id', 'name', 'description', 'cover_photo', 'avatar',
            'privacy', 'created_by', 'members_count',
            'is_member', 'my_role', 'created_at',
        ]
        read_only_fields = ['created_by', 'members_count']

    def get_is_member(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.memberships.filter(user=request.user).exists()
        return False

    def get_my_role(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            m = obj.memberships.filter(user=request.user).first()
            return m.role if m else None
        return None
