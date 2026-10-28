import os
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

from django.core.exceptions import ImproperlyConfigured

DEBUG = os.environ.get('DEBUG', 'False') == 'True'
_DEV_SECRET_KEY = 'django-insecure-dev-key-change-in-production'
SECRET_KEY = os.environ.get('SECRET_KEY', _DEV_SECRET_KEY if DEBUG else '')
if not DEBUG and (not SECRET_KEY or SECRET_KEY.startswith('django-insecure') or SECRET_KEY.startswith('change-me')):
    raise ImproperlyConfigured('Set a strong SECRET_KEY (50+ random characters) when DEBUG is off.')
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1,django').split(',')

# ============================================================
# Application Definition
# ============================================================
INSTALLED_APPS = [
    # Prometheus must be first
    'django_prometheus',

    # Django core
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'channels',
    'django_celery_beat',
    'django_celery_results',
    'django_filters',
    'drf_spectacular',

    # Local apps
    'core.apps.CoreConfig',
    'moderation.apps.ModerationConfig',
    'retrieval.apps.RetrievalConfig',
    'assistant.apps.AssistantConfig',
    'users.apps.UsersConfig',
    'posts.apps.PostsConfig',
    'chats.apps.ChatsConfig',
    'notifications.apps.NotificationsConfig',
    'groups.apps.GroupsConfig',
    'marketplace.apps.MarketplaceConfig',
    'watch.apps.WatchConfig',
    'pages.apps.PagesConfig',
]

MIDDLEWARE = [
    'django_prometheus.middleware.PrometheusBeforeMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_prometheus.middleware.PrometheusAfterMiddleware',
]

ROOT_URLCONF = 'andromeda.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'andromeda.wsgi.application'
ASGI_APPLICATION = 'andromeda.asgi.application'

# ============================================================
# Databases
# ============================================================
DATABASES = {
    'default': {
        'ENGINE': 'django_prometheus.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'andromeda'),
        'USER': os.environ.get('POSTGRES_USER', 'andromeda'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'andromeda_secret'),
        'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
        'OPTIONS': {'connect_timeout': 10},
    }
}

# Neo4j (neomodel)
NEOMODEL_NEO4J_BOLT_URL = os.environ.get(
    'NEO4J_BOLT_URL', 'bolt://neo4j:andromeda_secret@localhost:7687'
)
NEO4J_ENABLED = os.environ.get('NEO4J_ENABLED', 'True') == 'True'
NEOMODEL_SIGNALS = True
NEOMODEL_FORCE_TIMEZONE = True

# ============================================================
# Caching (Redis)
# ============================================================
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

CACHES = {
    'default': {
        'BACKEND': 'django_prometheus.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'KEY_PREFIX': 'andromeda',
    }
}

# ============================================================
# Django Channels (WebSockets)
# ============================================================
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [REDIS_URL],
            'capacity': 1500,
            'expiry': 10,
        },
    }
}

# ============================================================
# Celery (RabbitMQ broker, Redis result backend)
# ============================================================
CELERY_BROKER_URL = os.environ.get(
    'RABBITMQ_URL', 'amqp://andromeda:andromeda_secret@localhost:5672/andromeda'
)
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_SEND_SENT_EVENT = True  # lets celery-exporter see queued tasks
CELERY_TASK_TIME_LIMIT = 30 * 60

# Named queues
CELERY_TASK_QUEUES = {
    'default': {},
    'notifications': {},
    'messages': {},
    'emails': {},
    'video': {},  # ffmpeg transcoding; its own worker with concurrency 1
    'ai': {},  # assistant runs; its own worker so provider outages can't starve product queues
}
CELERY_TASK_DEFAULT_QUEUE = 'default'

# ── Periodic tasks ────────────────────────────────────────────
from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    'cleanup-old-notifications': {
        'task': 'notifications.tasks.cleanup_old_notifications',
        'schedule': crontab(hour=3, minute=0),
    },
    'daily-notification-digest': {
        'task': 'notifications.tasks.send_daily_digests',
        'schedule': crontab(hour=17, minute=0),
    },
    'weekly-listing-digest': {
        'task': 'notifications.tasks.send_listing_digests',
        'schedule': crontab(day_of_week='sat', hour=8, minute=0),
    },
    'erase-due-accounts': {
        'task': 'users.tasks.erase_due_accounts',
        'schedule': crontab(hour=2, minute=30),
    },
    'expire-data-exports': {
        'task': 'users.tasks.expire_data_exports',
        'schedule': crontab(hour=2, minute=45),
    },
    'assistant-housekeeping': {
        'task': 'assistant.tasks.housekeeping',
        'schedule': crontab(minute='*/5'),
    },
    'watch-requeue-stuck-videos': {
        'task': 'watch.tasks.requeue_stuck_videos',
        'schedule': crontab(minute=17),
    },
}

# ============================================================
# REST Framework
# ============================================================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'core.auth.AndromedaJWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'core.throttles.WriteRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': os.environ.get('THROTTLE_ANON', '60/min'),
        'user': os.environ.get('THROTTLE_USER', '600/min'),
        'write': os.environ.get('THROTTLE_WRITE', '60/min'),
        'auth': os.environ.get('THROTTLE_AUTH', '10/min'),
        'ws_ticket': os.environ.get('THROTTLE_WS_TICKET', '30/min'),
        'ai': os.environ.get('THROTTLE_AI', '30/hour'),
        'search': os.environ.get('THROTTLE_SEARCH', '300/hour'),
        'report': os.environ.get('THROTTLE_REPORT', '30/hour'),
        'export': os.environ.get('THROTTLE_EXPORT', '2/day'),
        'group_invite': os.environ.get('THROTTLE_GROUP_INVITE', '20/min'),
        'assistant': os.environ.get('THROTTLE_ASSISTANT', '60/hour'),
        'mcp': os.environ.get('THROTTLE_MCP', '120/min'),
    },
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Andromeda API',
    'DESCRIPTION': 'REST API for the Andromeda social platform.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    # Schema and docs require authentication outside DEBUG.
    'SERVE_PERMISSIONS': ['rest_framework.permissions.AllowAny' if DEBUG
                          else 'rest_framework.permissions.IsAdminUser'],
}

# Upload limits (the per-type caps live in core/validators.py).
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 200
DATA_UPLOAD_MAX_NUMBER_FILES = 10

# ============================================================
# JWT
# ============================================================
# Access tokens live in browser memory only. The refresh token is an
# HttpOnly, SameSite=Strict cookie scoped to the auth endpoints, so script
# injection can't read it and other sites can't send it.
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}
REFRESH_COOKIE_NAME = 'andromeda_refresh'
REFRESH_COOKIE_PATH = '/api/auth/'
REFRESH_COOKIE_SECURE = not DEBUG

# ============================================================
# Security headers & cookies
# ============================================================
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Strict'
CSRF_COOKIE_SAMESITE = 'Strict'
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if o]
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    # Set SECURE_SSL_REDIRECT / HSTS once TLS terminates in front of the app.
    SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'False') == 'True'
    SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '0'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
    SECURE_HSTS_PRELOAD = False

ADMIN_URL = os.environ.get('ADMIN_URL', 'admin/')

# ── AI service (internal; holds every model/provider key) ─────
# Web Push (VAPID). Generate a key pair with `python manage.py vapid_keys`;
# push stays off until both keys are set.
VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '')
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
VAPID_SUBJECT = os.environ.get('VAPID_SUBJECT', 'mailto:security@andromeda.local')
# The server POSTs to subscription endpoints, so only known push services are accepted.
WEB_PUSH_ALLOWED_HOSTS = ['fcm.googleapis.com', 'updates.push.services.mozilla.com', 'push.services.mozilla.com',
                          'push.apple.com', 'notify.windows.com']

AI_SERVICE_URL = os.environ.get('AI_SERVICE_URL', '')
AI_SERVICE_SECRET = os.environ.get('AI_SERVICE_SECRET', '')
AI_MODERATION_ENABLED = os.environ.get('AI_MODERATION_ENABLED', 'True') == 'True'
AI_SEARCH_ENABLED = os.environ.get('AI_SEARCH_ENABLED', 'True') == 'True'
# Listwise LLM rerank of the fused top results. Off by default: in the
# retrieval ablation (manage.py eval_retrieval) it added +0.01 recall@10 for
# ~2 s of latency.
AI_SEARCH_RERANK = os.environ.get('AI_SEARCH_RERANK', 'False') == 'True'
# LLM query rewrite for the search box. Off by default for the same reason;
# Ask Andromeda always rewrites, since it's making a model call anyway.
AI_SEARCH_REWRITE = os.environ.get('AI_SEARCH_REWRITE', 'False') == 'True'
if AI_SERVICE_SECRET and len(AI_SERVICE_SECRET) < 32:
    raise ImproperlyConfigured('AI_SERVICE_SECRET must be at least 32 characters.')

# ── Watch (video processing) ──────────────────────────────────
WATCH_MAX_DURATION_SECONDS = int(os.environ.get('WATCH_MAX_DURATION_SECONDS', 20 * 60))
WATCH_MAX_PROCESSING_PER_USER = int(os.environ.get('WATCH_MAX_PROCESSING_PER_USER', 3))
# Audio sent for captions is mono 16 kHz Opus (~3 MB per 20 min); the AI
# service refuses anything over 25 MB.
WATCH_MAX_CAPTION_AUDIO_BYTES = 24 * 1024 * 1024
# Signed playback links for videos that aren't on the public prefix.
WATCH_STREAM_TOKEN_MAX_AGE = 6 * 60 * 60
PASSWORD_RESET_TIMEOUT = 60 * 60  # 1 hour
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost')
# Bump when the terms or privacy policy change; consents record the version agreed to.
POLICY_VERSION = '2026-10-28'

# ============================================================
# CORS
# ============================================================
CORS_ALLOWED_ORIGINS = os.environ.get(
    'CORS_ALLOWED_ORIGINS',
    'http://localhost,http://localhost:80,http://localhost:4200'
).split(',')
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept', 'accept-encoding', 'authorization',
    'content-type', 'dnt', 'origin', 'user-agent',
    'x-csrftoken', 'x-requested-with',
]

# ============================================================
# Auth
# ============================================================
AUTH_USER_MODEL = 'users.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ============================================================
# Static & Media Files
# ============================================================
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ── MinIO / S3 Object Storage ──────────────────────────────────
# Only keys under ``public/`` are anonymously readable (bucket policy in
# docker-compose). Chat attachments live under ``private/`` and are streamed
# through an authenticated endpoint after a membership check.
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
_MINIO_ENDPOINT = os.environ.get('MINIO_ENDPOINT', '')
if _MINIO_ENDPOINT:
    STORAGES['default'] = {'BACKEND': 'storages.backends.s3.S3Storage'}
    AWS_S3_ENDPOINT_URL = _MINIO_ENDPOINT
    AWS_S3_URL_PROTOCOL = os.environ.get('AWS_S3_URL_PROTOCOL', 'http:')
    AWS_S3_USE_SSL = AWS_S3_URL_PROTOCOL == 'https:'
    AWS_S3_ADDRESSING_STYLE = 'path'
    AWS_ACCESS_KEY_ID = os.environ.get('MINIO_ACCESS_KEY', 'andromeda')
    AWS_SECRET_ACCESS_KEY = os.environ.get('MINIO_SECRET_KEY', 'andromeda_secret')
    AWS_STORAGE_BUCKET_NAME = os.environ.get('MINIO_BUCKET', 'andromeda-media')
    # Public URLs go through the nginx /media/ proxy; MinIO itself isn't exposed.
    AWS_S3_CUSTOM_DOMAIN = os.environ.get(
        'MINIO_EXTERNAL_URL', 'http://localhost:4200/media'
    ).replace('http://', '').replace('https://', '').rstrip('/')
    AWS_QUERYSTRING_AUTH = False
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None  # access is governed by the bucket's prefix policy

# ============================================================
# Email
# ============================================================
EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend'
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'Andromeda <noreply@andromeda.social>')

# ============================================================
# Internationalisation
# ============================================================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ============================================================
# Logging
# ============================================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'celery': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
}
