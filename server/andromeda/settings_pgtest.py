"""Test settings against a real PostgreSQL with pgvector (CI integration job)."""
import os

from .settings_test import *  # noqa: F401, F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'andromeda'),
        'USER': os.environ.get('POSTGRES_USER', 'andromeda'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'andromeda_ci'),
        'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
    }
}
