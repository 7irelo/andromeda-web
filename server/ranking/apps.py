from django.apps import AppConfig


class RankingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ranking'
    verbose_name = 'Feed ranking'

    def ready(self):
        from . import metrics, signals  # noqa: F401
        metrics.register_collectors()
