from django.contrib import admin
from .models import ChannelSubscription, Video, WatchProgress


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ['title', 'uploader', 'status', 'captions_status', 'views_count', 'likes_count', 'created_at']
    list_filter = ['status', 'captions_status', 'is_public']
    readonly_fields = ['asset_root', 'asset_id', 'asset_files', 'renditions', 'failure_reason',
                       'processing_started_at', 'subscribers_notified_at']


admin.site.register(WatchProgress)
admin.site.register(ChannelSubscription)
