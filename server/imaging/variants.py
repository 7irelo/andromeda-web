"""
Resized WebP variants of uploaded images, for ``srcset``.

Each variant is a fixed width (never upscaled), stored next to the original
with a predictable name, ``<original stem>.w<width>.webp``, so serializers can
build URLs without a lookup. They're made from the already-sanitised upload
(``core.validators.sanitize_image`` strips metadata first), so they carry no
EXIF either. Animated GIFs keep only their original.
"""
import io
import logging
from pathlib import PurePosixPath

from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)

POST_WIDTHS = {'thumb': 320, 'medium': 1080}
AVATAR_WIDTHS = {'thumb': 96, 'medium': 320}
WEBP_QUALITY = 80
_SOURCE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def has_variants(name):
    return bool(name) and PurePosixPath(name).suffix.lower() in _SOURCE_EXTENSIONS


def variant_name(name, width):
    p = PurePosixPath(name)
    return str(p.with_name(f'{p.stem}.w{int(width)}.webp'))


def variant_names(name, widths):
    return [variant_name(name, w) for w in widths.values()] if has_variants(name) else []


def _encode(img, width):
    if img.width > width:
        img = img.resize((width, max(1, round(img.height * width / img.width))), Image.Resampling.LANCZOS)
    if img.mode not in ('RGB', 'RGBA'):
        img = img.convert('RGBA' if 'A' in img.getbands() or img.mode == 'P' else 'RGB')
    buf = io.BytesIO()
    img.save(buf, format='WEBP', quality=WEBP_QUALITY, method=4)
    return buf.getvalue()


def generate(field_file, widths):
    """Write every variant of ``field_file``. Returns the stored names (empty if the file has none)."""
    name = field_file.name if field_file else ''
    if not has_variants(name):
        return []
    try:
        field_file.open('rb')
        try:
            img = Image.open(field_file)
            img.load()
        finally:
            field_file.close()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
        logger.warning('Could not read %s for variants', name, exc_info=True)
        return []
    storage = field_file.storage
    written = []
    for width in widths.values():
        key = variant_name(name, width)
        data = _encode(img, width)
        if storage.exists(key):
            storage.delete(key)
        saved = storage.save(key, ContentFile(data))
        if saved != key:  # the URL is derived from the name, so it must land exactly there
            storage.delete(saved)
            raise OSError(f'storage renamed {key} to {saved}')
        written.append(key)
    return written


def delete(storage, name, widths):
    for key in variant_names(name, widths):
        try:
            storage.delete(key)
        except Exception:
            logger.warning('Could not delete %s', key, exc_info=True)


def urls(field_file, widths, request=None):
    """``{'thumb': url, 'medium': url, 'srcset': 'url 320w, url 1080w'}``, or None when there are no variants."""
    name = field_file.name if field_file else ''
    if not has_variants(name):
        return None
    storage = field_file.storage
    out = {}
    parts = []
    for label, width in widths.items():
        url = storage.url(variant_name(name, width))
        if request is not None:
            url = request.build_absolute_uri(url)
        out[label] = url
        parts.append(f'{url} {width}w')
    out['srcset'] = ', '.join(parts)
    return out
