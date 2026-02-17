from rest_framework import serializers
from .models import Page
from users.serializers import UserSerializer


class PageSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    is_following = serializers.SerializerMethodField()

    class Meta:
        model = Page
        fields = [
            'id', 'name', 'username', 'description', 'category',
            'avatar', 'cover_photo', 'website', 'email', 'phone',
            'is_verified', 'followers_count', 'created_by', 'is_following', 'created_at',
        ]
        read_only_fields = ['created_by', 'followers_count', 'is_verified']

    def get_is_following(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.followers.filter(user=request.user).exists()
        return False
