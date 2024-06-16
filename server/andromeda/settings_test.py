"""
Test-specific Django settings.

Key differences from production settings:
  - SQLite (in-memory) — no Postgres container needed
  - Neo4j disabled — graph operations are mocked in tests
  - Redis stubbed with fake backend — no Redis container needed
  - Celery runs tasks eagerly in-process — no RabbitMQ needed
  - Password hashing uses MD5 — makes tests ~10× faster
"""
from .settings import *  # noqa: F401, F403

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
SECRET_KEY = "test-secret-key-not-used-in-production"
