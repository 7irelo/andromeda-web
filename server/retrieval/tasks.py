"""
Keep the embedding index in step with content.

Indexing runs after commit, off the request path, and is idempotent: a
document whose text hasn't changed (same hash) isn't re-embedded, so retries
and duplicate events cost nothing.
"""
import hashlib
import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction

from core import ai_client
from . import documents
from .models import Embedding

logger = logging.getLogger(__name__)
SYSTEM_USER = 0  # the AI service gives background work its own allowance
KINDS = ('posts', 'listings', 'groups', 'pages', 'videos')


def enabled():
    return settings.AI_SEARCH_ENABLED and ai_client.enabled()


def queue_index(kind, object_id):
    if enabled():
        transaction.on_commit(lambda: index_object.delay(kind, object_id))


def embed(texts, user_id=SYSTEM_USER):
    return ai_client.call('/v1/embed', {'texts': texts}, user_id=user_id)


@shared_task(name='retrieval.tasks.index_object', queue='default', autoretry_for=(ai_client.AIUnavailable,),
             retry_backoff=True, retry_backoff_max=600, max_retries=6)
def index_object(kind, object_id):
    doc = documents.load(kind, object_id)
    if doc is None:
        Embedding.objects.filter(kind=kind, object_id=object_id).delete()
        return 'removed'
    pieces = documents.chunks(doc)
    if not pieces:
        Embedding.objects.filter(kind=kind, object_id=object_id).delete()
        return 'empty'
    digest = hashlib.sha256('\x1e'.join(pieces).encode()).hexdigest()
    existing = Embedding.objects.filter(kind=kind, object_id=object_id)
    if existing.count() == len(pieces) and not existing.exclude(content_hash=digest).exists():
        return 'unchanged'
    res = embed(pieces)
    with transaction.atomic():
        existing.delete()
        Embedding.objects.bulk_create([
            Embedding(kind=kind, object_id=object_id, chunk_ix=i, text=text, content_hash=digest,
                      vector=vec, model=res['model'])
            for i, (text, vec) in enumerate(zip(pieces, res['vectors'], strict=True))
        ])
    return 'indexed'


@shared_task(name='retrieval.tasks.remove_object', queue='default')
def remove_object(kind, object_id):
    Embedding.objects.filter(kind=kind, object_id=object_id).delete()
