import io

import pytest
from botocore.exceptions import ClientError
from django.contrib.auth import get_user_model
from django.core import signing
from django.urls import reverse
from rest_framework.test import APIClient

from watch import uploads
from watch.models import Video

User = get_user_model()
MP4 = b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 64


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.policies = []

    def generate_presigned_post(self, Bucket, Key, Fields, Conditions, ExpiresIn):
        self.policies.append({'Bucket': Bucket, 'Key': Key, 'Fields': Fields, 'Conditions': Conditions,
                              'ExpiresIn': ExpiresIn})
        return {'url': f'http://minio:9000/{Bucket}', 'fields': {**Fields, 'key': Key, 'policy': 'p',
                                                                  'x-amz-signature': 's'}}

    def put(self, key, data, content_type='video/mp4'):
        self.objects[key] = (data, content_type)

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({'Error': {'Code': '404'}}, 'HeadObject')
        data, ct = self.objects[Key]
        return {'ContentLength': len(data), 'ContentType': ct}

    def get_object(self, Bucket, Key, Range):
        start, end = (int(x) for x in Range.split('=')[1].split('-'))
        return {'Body': io.BytesIO(self.objects[Key][0][start:end + 1])}

    def copy_object(self, Bucket, Key, CopySource, ContentType, MetadataDirective):
        self.objects[Key] = (self.objects[CopySource['Key']][0], ContentType)

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)


@pytest.fixture
def s3(monkeypatch):
    fake = FakeS3()
    monkeypatch.setattr(uploads, 'enabled', lambda: True)
    monkeypatch.setattr(uploads, '_s3', lambda: fake)
    monkeypatch.setattr(uploads, '_bucket', lambda: 'andromeda-media')
    return fake


@pytest.fixture
def user(db):
    return User.objects.create_user(username='ana', password='pass-1234567', email='ana@example.com')


@pytest.fixture
def client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def _start(client, size=len(MP4), content_type='video/mp4'):
    return client.post(reverse('watch-direct-upload'), {'content_type': content_type, 'size': size}, format='json')


def _complete(client, token, **extra):
    return client.post(reverse('watch-direct-upload-complete'), {'upload_token': token, 'title': 'Trip', **extra},
                       format='json')


class TestStart:
    def test_policy_pins_key_type_and_size(self, client, s3):
        resp = _start(client, size=1000)
        assert resp.status_code == 201
        policy = s3.policies[0]
        assert policy['Key'].startswith('private/uploads/') and policy['Key'].endswith('.mp4')
        assert ['content-length-range', 1, 1000] in policy['Conditions']
        assert {'Content-Type': 'video/mp4'} in policy['Conditions']
        assert policy['ExpiresIn'] == 15 * 60
        assert resp.data['url'] == '/media-upload/'  # never the internal MinIO address
        assert resp.data['fields']['key'] == policy['Key']

    def test_refuses_bad_types_and_oversized_files(self, client, s3):
        assert _start(client, content_type='text/html').status_code == 400
        assert _start(client, size=uploads.MAX_VIDEO_BYTES + 1).status_code == 400
        assert s3.policies == []

    def test_needs_object_storage(self, client):
        assert _start(client).status_code == 501

    def test_needs_sign_in(self, s3):
        assert _start(APIClient()).status_code == 401


class TestComplete:
    def test_valid_upload_is_moved_and_processed(self, client, s3, django_capture_on_commit_callbacks, monkeypatch):
        queued = []
        monkeypatch.setattr(uploads, 'queue_processing', queued.append)
        start = _start(client).data
        key = start['fields']['key']
        s3.put(key, MP4)

        resp = _complete(client, start['upload_token'], description='Holiday', is_public=False, tags=['travel'])

        assert resp.status_code == 201, resp.data
        video = Video.objects.get()
        assert video.video_file.name.startswith('private/watch/originals/')
        assert (video.title, video.is_public, video.tags) == ('Trip', False, ['travel'])
        assert video.status == Video.STATUS_PROCESSING and queued == [video.pk]
        assert key not in s3.objects and video.video_file.name in s3.objects
        # Completing twice can't create a second video.
        assert _complete(client, start['upload_token']).status_code == 400
        assert Video.objects.count() == 1

    def test_wrong_magic_bytes_are_rejected_and_deleted(self, client, s3):
        start = _start(client, size=100).data
        key = start['fields']['key']
        s3.put(key, b'<html><script>alert(1)</script>')
        resp = _complete(client, start['upload_token'])
        assert resp.status_code == 400
        assert key not in s3.objects and not Video.objects.exists()

    def test_wrong_content_type_is_rejected(self, client, s3):
        start = _start(client).data
        s3.put(start['fields']['key'], MP4, content_type='image/svg+xml')
        assert _complete(client, start['upload_token']).status_code == 400

    def test_missing_upload(self, client, s3):
        start = _start(client).data
        assert _complete(client, start['upload_token']).status_code == 400

    def test_someone_elses_token_is_refused(self, client, s3):
        start = _start(client).data
        s3.put(start['fields']['key'], MP4)
        other = APIClient()
        other.force_authenticate(User.objects.create_user(username='eve', password='pass-1234567', email='e@x.io'))
        assert _complete(other, start['upload_token']).status_code == 403
        assert not Video.objects.exists()

    def test_forged_token_is_refused(self, client, s3, user):
        forged = signing.dumps({'k': 'public/avatars/x.mp4', 'u': user.id, 't': 'video/mp4', 's': 10}, salt='nope')
        assert _complete(client, forged).status_code == 400
        rogue_key = signing.dumps({'k': 'public/avatars/x.mp4', 'u': user.id, 't': 'video/mp4', 's': 10},
                                  salt=uploads.UPLOAD_SALT)
        assert _complete(client, rogue_key).status_code == 400

    def test_processing_limit_applies(self, client, s3, user, settings):
        settings.WATCH_MAX_PROCESSING_PER_USER = 1
        Video.objects.create(uploader=user, title='busy', video_file='private/watch/originals/x.mp4')
        assert _start(client).status_code == 429
