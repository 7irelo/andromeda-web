from django.apps import AppConfig
import logging

class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'users'
    verbose_name = 'Users Application'

    def ready(self):
        # Set up logging for the app
        logging.basicConfig(
            format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
            level=logging.INFO
        )
        
        # Import and register signals
        try:
            import users.signals
        except ImportError as e:
            logging.error(f"Failed to import signals: {e}")
        
        # Any other app-specific setup
        self.setup_app_specific_config()

    def setup_app_specific_config(self):
        # Add any other initialization code here
        logging.info("Users app-specific setup completed.")
