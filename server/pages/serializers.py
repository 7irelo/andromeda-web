import random
import string

from django.utils.text import slugify
from rest_framework import serializers
from core.validators import sanitize_image
from .models import Page
from users.serializers import UserSerializer


class PageSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    is_following = serializers.SerializerMethodField()
    username = serializers.RegexField(r'^[a-z0-9][a-z0-9._-]{2,99}$', required=False, allow_blank=True)

    class Meta:
        model = Page
        fields = [
            'id', 'name', 'username', 'description', 'category',
            'avatar', 'cover_photo', 'website', 'email', 'phone',
            'is_verified', 'followers_count', 'created_by', 'is_following', 'created_at',
        ]
        read_only_fields = ['created_by', 'followers_count', 'is_verified']

    def validate_avatar(self, value):
        return sanitize_image(value) if value else value

    def validate_cover_photo(self, value):
        return sanitize_image(value) if value else value

    def get_is_following(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.followers.filter(user=request.user).exists()
        return False

    def create(self, validated_data):
        username = validated_data.get('username', '').strip()
        if not username:
            base = slugify(validated_data.get('name', 'page'))[:40] or 'page'
            username = base
            while Page.objects.filter(username=username).exists():
                suffix = ''.join(random.choices(string.digits, k=4))
                username = f'{base}-{suffix}'
            validated_data['username'] = username
        return super().create(validated_data)

    def validate_category(self, value):
        if not value:
            return Page.CATEGORY_OTHER
        normalised = value.strip().lower()
        valid = {choice for choice, _label in Page.CATEGORY_CHOICES}
        return normalised if normalised in valid else Page.CATEGORY_OTHER
