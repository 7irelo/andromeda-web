from django.apps import AppConfig


class AssistantConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'assistant'
    verbose_name = 'Andromeda Assistant'

    def ready(self):
        from . import signals  # noqa: F401
