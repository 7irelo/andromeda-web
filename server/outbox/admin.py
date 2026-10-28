from django.contrib import admin

from . import drain
from .models import GraphDrift, OutboxEvent


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display = ['id', 'kind', 'attempts', 'created_at', 'next_attempt_at', 'processed_at', 'dead_at']
    list_filter = ['kind', ('processed_at', admin.EmptyFieldListFilter), ('dead_at', admin.EmptyFieldListFilter)]
    readonly_fields = [f.name for f in OutboxEvent._meta.fields]
    actions = ['requeue']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.action(description='Retry selected dead-lettered events')
    def requeue(self, request, queryset):
        n = drain.requeue_dead(list(queryset.values_list('id', flat=True)))
        self.message_user(request, f'{n} event(s) queued again.')


@admin.register(GraphDrift)
class GraphDriftAdmin(admin.ModelAdmin):
    list_display = ['kind', 'last_run', 'total', 'checked_at']
    readonly_fields = ['kind', 'last_run', 'total', 'checked_at']

    def has_add_permission(self, request):
        return False
