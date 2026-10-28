from django.apps import AppConfig


class FeedcacheConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'feedcache'

    def ready(self):
        from . import signals
        signals.connect()
