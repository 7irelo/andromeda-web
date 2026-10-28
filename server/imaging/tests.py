import io

import pytest
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from rest_framework.test import APIClient

from core.validators import sanitize_image
from imaging import variants
from posts.models import Post, PostMedia

User = get_user_model()


def _png(width=1600, height=900, fmt='PNG'):
    buf = io.BytesIO()
    Image.new('RGB', (width, height), (200, 30, 30)).save(buf, format=fmt)
    return SimpleUploadedFile(f'photo.{fmt.lower()}', buf.getvalue(), content_type=f'image/{fmt.lower()}')


@pytest.fixture
def user(db):
    return User.objects.create_user(username='ana', password='pass-1234567', email='ana@example.com')


def _width(name):
    with default_storage.open(name, 'rb') as fh:
        img = Image.open(fh)
        return img.format, img.width


class TestNames:
    def test_variant_names_sit_next_to_the_original(self):
        assert variants.variant_name('public/posts/media/2026/10/abc.jpg', 320) == \
            'public/posts/media/2026/10/abc.w320.webp'

    def test_gifs_and_videos_have_none(self):
        assert variants.variant_names('public/x/a.gif', variants.POST_WIDTHS) == []
        assert variants.variant_names('public/x/a.mp4', variants.POST_WIDTHS) == []
        assert variants.urls(None, variants.POST_WIDTHS) is None


class TestGeneration:
    def test_post_media_gets_webp_variants_and_srcset(self, user):
        post = Post.objects.create(author=user, content='pic', post_type=Post.TYPE_IMAGE)
        media = PostMedia.objects.create(post=post, file=sanitize_image(_png()), media_type='image')
        thumb, medium = variants.variant_names(media.file.name, variants.POST_WIDTHS)
        assert _width(thumb) == ('WEBP', 320)
        assert _width(medium) == ('WEBP', 1080)

        out = variants.urls(media.file, variants.POST_WIDTHS)
        assert out['thumb'].endswith('.w320.webp') and out['medium'].endswith('.w1080.webp')
        assert out['srcset'] == f"{out['thumb']} 320w, {out['medium']} 1080w"

    def test_small_images_are_not_upscaled(self, user):
        post = Post.objects.create(author=user, content='pic', post_type=Post.TYPE_IMAGE)
        media = PostMedia.objects.create(post=post, file=sanitize_image(_png(200, 100)), media_type='image')
        thumb, medium = variants.variant_names(media.file.name, variants.POST_WIDTHS)
        assert _width(thumb)[1] == 200 and _width(medium)[1] == 200

    def test_avatar_change_generates_variants_and_deletion_removes_them(self, user, django_capture_on_commit_callbacks):
        user.avatar = sanitize_image(_png(800, 800, 'JPEG'))
        user.save()
        names = variants.variant_names(user.avatar.name, variants.AVATAR_WIDTHS)
        assert [_width(n)[1] for n in names] == [96, 320]
        with django_capture_on_commit_callbacks(execute=True):
            User.objects.get(pk=user.pk).delete()
        assert not any(default_storage.exists(n) for n in names)

    def test_unrelated_saves_do_not_regenerate(self, user, monkeypatch):
        user.avatar = sanitize_image(_png(400, 400))
        user.save()
        calls = []
        monkeypatch.setattr(variants, 'generate', lambda *a: calls.append(a))
        user = User.objects.get(pk=user.pk)
        user.bio = 'hello'
        user.save()
        assert calls == []

    def test_a_broken_variant_never_fails_the_upload(self, user, monkeypatch):
        def boom(*a):
            raise OSError('disk full')
        monkeypatch.setattr(variants, 'generate', boom)
        post = Post.objects.create(author=user, content='pic', post_type=Post.TYPE_IMAGE)
        PostMedia.objects.create(post=post, file=sanitize_image(_png()), media_type='image')
        assert PostMedia.objects.count() == 1


class TestSerializers:
    def test_post_and_author_payloads_are_srcset_ready(self, user):
        client = APIClient()
        client.force_authenticate(user)
        user.avatar = sanitize_image(_png(400, 400))
        user.save()
        resp = client.post(reverse('post-list'), {'content': 'two pics', 'images': [_png(), _png()]},
                           format='multipart')
        assert resp.status_code == 201, resp.content
        post = client.get(reverse('post-detail', kwargs={'pk': resp.data['id']})).data
        assert post['author']['avatar_variants']['srcset'].count('w,') == 1
        for media in post['media']:
            assert media['variants']['thumb'].startswith('http://testserver/')
            assert ' 1080w' in media['variants']['srcset']
        assert post['image_variants'] is None
