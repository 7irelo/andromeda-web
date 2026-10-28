from django.apps import AppConfig


class OutboxConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'outbox'

    def ready(self):
        from . import metrics
        metrics.register()
