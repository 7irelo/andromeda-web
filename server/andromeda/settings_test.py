"""
Test-specific Django settings.

Key differences from production settings:
  - SQLite (in-memory) — no Postgres container needed
  - Neo4j disabled — graph operations are mocked in tests
  - Redis stubbed with fake backend — no Redis container needed
  - Celery runs tasks eagerly in-process — no RabbitMQ needed
  - Password hashing uses MD5 — makes tests ~10× faster
"""
import os

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-0123456789-abcdefghijklmnopqrstuvwxyz")

from .settings import *  # noqa: F401, F403, E402

# ── Database: in-memory SQLite ─────────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# ── Neo4j: disable – neomodel will not attempt to connect ─────────────────────
NEOMODEL_NEO4J_BOLT_URL = "bolt://localhost:7687"  # never reached
NEOMODEL_SIGNALS = False
NEO4J_ENABLED = False

# ── Cache: in-memory dummy backend ────────────────────────────────────────────
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# ── Channels: in-memory layer (no Redis) ──────────────────────────────────────
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

# ── Celery: run tasks synchronously in the test process ───────────────────────
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

# ── Speed: fast password hasher ───────────────────────────────────────────────
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# ── Email: capture in memory ──────────────────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# ── Media: temp dir ───────────────────────────────────────────────────────────
import tempfile  # noqa: E402

MEDIA_ROOT = tempfile.mkdtemp()

# ── Misc ──────────────────────────────────────────────────────────────────────
DEBUG = False

# ── Throttling: generous limits so the suite isn't rate-limited ───────────────
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {
        "anon": "10000/min", "user": "10000/min", "write": "10000/min",
        "auth": "10000/min", "ws_ticket": "10000/min", "ai": "10000/min",
    },
}
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

AI_SERVICE_URL = ""
AI_SERVICE_SECRET = ""
