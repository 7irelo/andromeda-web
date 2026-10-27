from django.contrib import admin

from .models import ModerationAction, ModerationCase


@admin.register(ModerationCase)
class ModerationCaseAdmin(admin.ModelAdmin):
    list_display = ('id', 'content_type', 'object_id', 'author', 'decision', 'confidence', 'resolved', 'created_at')
    list_filter = ('decision', 'resolved', 'content_type', 'degraded')
    readonly_fields = [f.name for f in ModerationCase._meta.fields]


@admin.register(ModerationAction)
class ModerationActionAdmin(admin.ModelAdmin):
    list_display = ('case', 'moderator', 'action', 'created_at')
    readonly_fields = ('case', 'moderator', 'action', 'note', 'created_at')

    def has_delete_permission(self, request, obj=None):
        return False  # the audit log is append-only
