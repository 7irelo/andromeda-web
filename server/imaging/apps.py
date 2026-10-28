from django.apps import AppConfig


class ImagingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'imaging'

    def ready(self):
        from . import signals
        signals.connect()
