from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, FriendRequest, Follow, Block


@admin.register(User)
class AndromedaUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'full_name', 'is_verified', 'followers_count', 'created_at']
    list_filter = ['is_verified', 'is_staff', 'is_active']
    fieldsets = UserAdmin.fieldsets + (
        ('Profile', {'fields': ('bio', 'avatar', 'cover_photo', 'location', 'website', 'birth_date', 'is_verified')}),
        ('Stats', {'fields': ('followers_count', 'following_count', 'friends_count', 'posts_count')}),
    )
    readonly_fields = ['followers_count', 'following_count', 'friends_count', 'posts_count']


@admin.register(FriendRequest)
class FriendRequestAdmin(admin.ModelAdmin):
    list_display = ['sender', 'receiver', 'status', 'created_at']
    list_filter = ['status']


admin.site.register(Follow)
admin.site.register(Block)
