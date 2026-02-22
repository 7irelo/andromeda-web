from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, FriendRequest, Block


@admin.register(User)
class AndromedaUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'full_name', 'is_verified', 'friends_count', 'created_at']
    list_filter = ['is_verified', 'is_staff', 'is_active']
    fieldsets = UserAdmin.fieldsets + (
        ('Profile', {'fields': ('bio', 'avatar', 'cover_photo', 'location', 'website', 'birth_date', 'is_verified')}),
        ('Privacy', {'fields': (
            'privacy_profile', 'privacy_messages', 'privacy_friend_requests',
            'privacy_friends_list', 'default_post_privacy', 'show_online_status', 'searchable',
        )}),
        ('Stats', {'fields': ('friends_count', 'posts_count')}),
    )
    readonly_fields = ['friends_count', 'posts_count']


@admin.register(FriendRequest)
class FriendRequestAdmin(admin.ModelAdmin):
    list_display = ['sender', 'receiver', 'status', 'created_at']
    list_filter = ['status']


admin.site.register(Block)
