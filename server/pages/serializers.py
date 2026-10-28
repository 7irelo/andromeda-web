import random
import string

from django.utils.text import slugify
from rest_framework import serializers
from core import viewer_cache
from core.validators import sanitize_image
from .models import Page, PageAdmin, PageFollow
from users.serializers import UserSerializer


class PageSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    is_following = serializers.SerializerMethodField()
    my_role = serializers.SerializerMethodField()
    username = serializers.RegexField(r'^[a-z0-9][a-z0-9._-]{2,99}$', required=False, allow_blank=True)

    class Meta:
        model = Page
        fields = [
            'id', 'name', 'username', 'description', 'category',
            'avatar', 'cover_photo', 'website', 'email', 'phone',
            'is_verified', 'followers_count', 'created_by', 'is_following', 'my_role', 'created_at',
        ]
        # is_verified is granted by staff only (PageViewSet.verify / the Django admin).
        read_only_fields = ['created_by', 'followers_count', 'is_verified']

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('A page needs a name.')
        return value

    def validate_description(self, value):
        if len(value) > 5000:
            raise serializers.ValidationError('Keep the description under 5000 characters.')
        return value

    def validate_username(self, value):
        value = value.strip()
        if value and Page.objects.filter(username=value).exclude(
            pk=getattr(self.instance, 'pk', None)
        ).exists():
            raise serializers.ValidationError('This username is taken.')
        return value

    def update(self, instance, validated_data):
        # Blank means "keep the current one" on edit; only create generates a username.
        if not validated_data.get('username', 'keep'):
            validated_data.pop('username')
        return super().update(instance, validated_data)

    def get_my_role(self, obj):
        request = self.context.get('request')
        if not (request and request.user.is_authenticated):
            return None
        if obj.created_by_id == request.user.id:
            return PageAdmin.ROLE_ADMIN
        user = request.user
        return viewer_cache.memo(self, ('page_roles', user.id), lambda: dict(
            PageAdmin.objects.filter(user=user).values_list('page_id', 'role'))).get(obj.id)

    def validate_avatar(self, value):
        return sanitize_image(value) if value else value

    def validate_cover_photo(self, value):
        return sanitize_image(value) if value else value

    def get_is_following(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            user = request.user
            return obj.id in viewer_cache.memo(self, ('page_follows', user.id), lambda: set(
                PageFollow.objects.filter(user=user).values_list('page_id', flat=True)))
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


class PageAdminSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = PageAdmin
        fields = ['id', 'user', 'role']
        read_only_fields = fields
