"""
Direct-to-object-storage uploads for large videos.

Streaming a 500 MB file through nginx and Django ties up a worker for the
whole upload. Instead:

1. ``POST /api/watch/uploads/`` with ``{content_type, size}`` returns a
   presigned POST policy for one random key under ``private/uploads/``. The
   policy pins the bucket, the exact key, the content type and a size range of
   1 byte to the declared size (at most ``MAX_VIDEO_BYTES``), and expires in
   15 minutes. The browser posts the file to ``WATCH_DIRECT_UPLOAD_URL``,
   which nginx proxies (POST only) to the bucket. Nothing under
   ``private/`` is readable anonymously.
2. ``POST /api/watch/uploads/complete/`` with the signed ``upload_token`` and
   the video's details checks the stored object (owner, size, content type,
   magic bytes), moves it to ``private/watch/originals/`` and hands it to the
   existing processing pipeline. A file that fails a check is deleted.

Abandoned uploads expire through a bucket lifecycle rule on
``private/uploads/`` (see docker-compose ``createbuckets``).
"""
import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import APIException, PermissionDenied, Throttled, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.validators import MAX_VIDEO_BYTES, MB, RandomFilename, is_video_header
from .models import Video
from .serializers import VideoSerializer
from .tasks import queue_processing

logger = logging.getLogger(__name__)

UPLOAD_SALT = 'watch.direct-upload'
POLICY_SECONDS = 15 * 60
# The token outlives the policy so a slow upload that finished in time can still complete.
TOKEN_MAX_AGE = 3 * 60 * 60
CONTENT_TYPES = {'video/mp4': '.mp4', 'video/quicktime': '.mov', 'video/webm': '.webm', 'video/x-matroska': '.mkv'}
ORIGINALS = RandomFilename('private/watch/originals')


class Unavailable(APIException):
    status_code = status.HTTP_501_NOT_IMPLEMENTED
    default_detail = 'Direct uploads need object storage. Upload through /api/watch/videos/ instead.'


def enabled():
    return hasattr(default_storage, 'bucket_name') and hasattr(default_storage, 'connection')


def _s3():
    return default_storage.connection.meta.client


def _bucket():
    return default_storage.bucket_name


def _check_capacity(user):
    busy = Video.objects.filter(uploader=user, status=Video.STATUS_PROCESSING).count()
    if busy >= settings.WATCH_MAX_PROCESSING_PER_USER:
        raise Throttled(detail='Wait for your other uploads to finish processing.')


class StartSerializer(serializers.Serializer):
    content_type = serializers.ChoiceField(choices=sorted(CONTENT_TYPES))
    size = serializers.IntegerField(min_value=1, max_value=MAX_VIDEO_BYTES,
                                    error_messages={'max_value': f'Videos must be smaller than {MAX_VIDEO_BYTES // MB} MB.'})


class CompleteSerializer(serializers.Serializer):
    upload_token = serializers.CharField(max_length=1000)
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, default='', max_length=5000)
    is_public = serializers.BooleanField(required=False, default=True)
    tags = serializers.ListField(child=serializers.CharField(max_length=100), required=False, default=list)

    def validate_tags(self, value):
        return VideoSerializer().validate_tags(value)


class DirectUploadView(APIView):
    """Start a direct upload: returns where and how to POST the file."""

    def post(self, request):
        if not enabled():
            raise Unavailable()
        body = StartSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        _check_capacity(request.user)
        content_type, size = body.validated_data['content_type'], body.validated_data['size']
        key = f'private/uploads/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{CONTENT_TYPES[content_type]}'
        policy = _s3().generate_presigned_post(
            Bucket=_bucket(), Key=key,
            Fields={'Content-Type': content_type},
            Conditions=[{'Content-Type': content_type}, ['content-length-range', 1, size]],
            ExpiresIn=POLICY_SECONDS,
        )
        token = signing.dumps({'k': key, 'u': request.user.id, 't': content_type, 's': size}, salt=UPLOAD_SALT)
        return Response({
            # The bucket is only reachable through nginx's POST-only proxy.
            'url': settings.WATCH_DIRECT_UPLOAD_URL,
            'fields': policy['fields'],
            'upload_token': token,
            'max_bytes': size,
            'expires_at': (timezone.now() + timedelta(seconds=POLICY_SECONDS)).isoformat(),
        }, status=status.HTTP_201_CREATED)


def _discard(key):
    try:
        _s3().delete_object(Bucket=_bucket(), Key=key)
    except Exception:
        logger.warning('Could not delete rejected upload %s', key, exc_info=True)


def _inspect(key, claims):
    """Size, type and magic-byte checks on the stored object. Raises ValidationError (and deletes it) on failure."""
    from botocore.exceptions import ClientError

    s3 = _s3()
    try:
        head = s3.head_object(Bucket=_bucket(), Key=key)
    except ClientError:
        raise ValidationError({'upload_token': 'No uploaded file was found. Upload it, then try again.'}) from None
    size = int(head.get('ContentLength') or 0)
    problem = None
    if not 0 < size <= min(int(claims['s']), MAX_VIDEO_BYTES):
        problem = 'The uploaded file is larger than declared.'
    elif head.get('ContentType') != claims['t']:
        problem = 'The uploaded file has the wrong type.'
    else:
        first = s3.get_object(Bucket=_bucket(), Key=key, Range='bytes=0-15')['Body'].read(16)
        if not is_video_header(first):
            problem = 'Unsupported video type. Use MP4, MOV or WebM.'
    if problem:
        _discard(key)
        raise ValidationError({'upload_token': problem})
    return size


class DirectUploadCompleteView(APIView):
    """Finish a direct upload: validate the stored file and start processing."""

    def post(self, request):
        if not enabled():
            raise Unavailable()
        body = CompleteSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        try:
            claims = signing.loads(data['upload_token'], salt=UPLOAD_SALT, max_age=TOKEN_MAX_AGE)
        except signing.BadSignature:
            raise ValidationError({'upload_token': 'This upload has expired. Start again.'}) from None
        if claims.get('u') != request.user.id:
            raise PermissionDenied('This upload belongs to someone else.')
        key = claims['k']
        if not (isinstance(key, str) and key.startswith('private/uploads/') and '..' not in key):
            raise ValidationError({'upload_token': 'Invalid upload.'})
        # One completion per upload, even if the client retries concurrently.
        lock = f'watch:direct-upload:{key}'
        if not cache.add(lock, 1, 10 * 60):
            raise ValidationError({'upload_token': 'This upload is already being completed.'})
        try:
            _check_capacity(request.user)
            _inspect(key, claims)
            dest = ORIGINALS(None, f'video{CONTENT_TYPES[claims["t"]]}')
            s3 = _s3()
            s3.copy_object(Bucket=_bucket(), Key=dest, CopySource={'Bucket': _bucket(), 'Key': key},
                           ContentType=claims['t'], MetadataDirective='REPLACE')
            _discard(key)
            with transaction.atomic():
                video = Video.objects.create(
                    uploader=request.user, title=data['title'], description=data['description'],
                    is_public=data['is_public'], tags=data['tags'], status=Video.STATUS_PROCESSING,
                    video_file=dest,
                )
                queue_processing(video.pk)
        except Exception:
            cache.delete(lock)
            raise
        return Response(VideoSerializer(video, context={'request': request}).data, status=status.HTTP_201_CREATED)
