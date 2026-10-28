from django.contrib import admin

from .models import Page


@admin.register(Page)
class PageModelAdmin(admin.ModelAdmin):
    list_display = ['name', 'username', 'category', 'is_verified', 'followers_count', 'created_at']
    list_filter = ['is_verified', 'category']
    search_fields = ['name', 'username']
    actions = ['mark_verified', 'mark_unverified']

    @admin.action(description='Mark selected pages as verified')
    def mark_verified(self, request, queryset):
        queryset.update(is_verified=True)

    @admin.action(description='Remove verification from selected pages')
    def mark_unverified(self, request, queryset):
        queryset.update(is_verified=False)
