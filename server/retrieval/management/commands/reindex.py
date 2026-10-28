"""
Build or refresh the semantic search index.

    python manage.py reindex                 # everything, skipping unchanged documents
    python manage.py reindex --kind posts    # one content type

Documents are embedded in batches under the system identity, so a full
rebuild doesn't spend any member's AI allowance.
"""
import hashlib

from django.core.management.base import BaseCommand
from django.db import transaction

from retrieval import documents
from retrieval.models import Embedding
from retrieval.tasks import KINDS, embed

BATCH = 64


def _models():
    from groups.models import Group
    from marketplace.models import Listing
    from pages.models import Page
    from posts.models import Post
    from watch.models import Video
    return {'posts': Post, 'listings': Listing, 'groups': Group, 'pages': Page, 'videos': Video}


class Command(BaseCommand):
    help = 'Embed content for semantic search.'

    def add_arguments(self, parser):
        parser.add_argument('--kind', choices=KINDS, action='append')

    def handle(self, *args, kind=None, **opts):
        models = _models()
        for k in kind or KINDS:
            ids = list(models[k].objects.values_list('pk', flat=True).order_by('pk'))
            pending, done, skipped = [], 0, 0
            for oid in ids:
                doc = documents.load(k, oid)
                pieces = documents.chunks(doc) if doc else []
                if not pieces:
                    Embedding.objects.filter(kind=k, object_id=oid).delete()
                    continue
                digest = hashlib.sha256('\x1e'.join(pieces).encode()).hexdigest()
                current = Embedding.objects.filter(kind=k, object_id=oid)
                if current.count() == len(pieces) and not current.exclude(content_hash=digest).exists():
                    skipped += 1
                    continue
                pending.extend((oid, i, text, digest) for i, text in enumerate(pieces))
                if len(pending) >= BATCH:
                    done += self._flush(k, pending)
                    pending = []
            if pending:
                done += self._flush(k, pending)
            self.stdout.write(f'{k}: {done} chunks embedded, {skipped} documents unchanged')

    def _flush(self, kind, pending):
        res = embed([p[2] for p in pending])
        with transaction.atomic():
            Embedding.objects.filter(kind=kind, object_id__in={p[0] for p in pending}).delete()
            Embedding.objects.bulk_create([
                Embedding(kind=kind, object_id=oid, chunk_ix=i, text=text, content_hash=digest, vector=vec,
                          model=res['model'])
                for (oid, i, text, digest), vec in zip(pending, res['vectors'], strict=True)
            ])
        return len(pending)
