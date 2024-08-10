from django.contrib import admin
from .models import Video


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ['title', 'uploader', 'status', 'views_count', 'likes_count', 'created_at']
    list_filter = ['status', 'is_public']
