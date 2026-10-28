from django.apps import AppConfig


class ObservabilityConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'observability'

    def ready(self):
        from . import errors, request_id, tracing

        request_id.connect_celery()
        errors.setup()
        tracing.setup()
