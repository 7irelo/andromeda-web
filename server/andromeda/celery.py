import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'andromeda.settings')

app = Celery('andromeda')

# Read config from Django settings, namespace CELERY_
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

# ── Queue definitions ──────────────────────────────────────────────────────────
app.conf.task_routes = {
    'notifications.tasks.*': {'queue': 'notifications'},
    'chats.tasks.*': {'queue': 'messages'},
    'users.tasks.*': {'queue': 'emails'},
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
