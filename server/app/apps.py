from django.apps import AppConfig
import logging

class BaseConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app'
    verbose_name = 'Base Application'

    def ready(self):
        # Set up logging for the app
        logging.basicConfig(
            format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
            level=logging.INFO
        )
        
        # Import and register signals
        import app.signals

        # Any other app-specific setup
