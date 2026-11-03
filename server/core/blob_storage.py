"""
Vercel Blob as Django's file storage, for deployments with no writable disk.

The store is private, so nothing in it has a public URL. Names keep their
``public/`` and ``private/`` prefixes: ``public/`` files are served by
``core.media_views`` and ``private/`` files by the existing authenticated
endpoints, which keeps the same access rules as the MinIO setup.
"""
from urllib.parse import quote

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


def _sdk():
    from vercel.blob import sync as blob  # only installed on Vercel

    return blob


@deconstructible
class BlobStorage(Storage):
    def _save(self, name, content):
        content.seek(0)
        _sdk().put_blob(name, content.read(), access='private', content_type=getattr(content, 'content_type', None))
        return name

    def _open(self, name, mode='rb'):
        if mode != 'rb':
            raise ValueError('Blob files are read-only once stored.')
        return ContentFile(_sdk().get_blob(name, access='private').body, name=name)

    def exists(self, name):
        try:
            _sdk().head_blob(name)
        except FileNotFoundError:
            return False
        return True

    def delete(self, name):
        if name:
            _sdk().delete_blob(name)

    def size(self, name):
        return _sdk().head_blob(name).size

    def url(self, name):
        return f'{settings.MEDIA_URL}{quote(name)}'

    def get_modified_time(self, name):
        return _sdk().head_blob(name).uploaded_at
