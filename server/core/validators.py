"""
Upload validation.

Content is sniffed rather than trusted from the extension or the client's
content type. Images are re-encoded, which strips EXIF metadata such as GPS
coordinates and neutralises polyglot payloads. Stored filenames are random so
media URLs can't be guessed.
"""
import io
import uuid
from pathlib import PurePosixPath

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.utils import timezone
from django.utils.deconstruct import deconstructible
from PIL import Image, UnidentifiedImageError

MB = 1024 * 1024
MAX_IMAGE_BYTES = 10 * MB
MAX_VIDEO_BYTES = 500 * MB
MAX_FILE_BYTES = 25 * MB
ALLOWED_IMAGE_FORMATS = {'JPEG': ('jpg', 'image/jpeg'), 'PNG': ('png', 'image/png'),
                         'WEBP': ('webp', 'image/webp'), 'GIF': ('gif', 'image/gif')}

# Refuse decompression bombs (~ 8000 x 5000 pixels).
Image.MAX_IMAGE_PIXELS = 40_000_000


@deconstructible
class RandomFilename:
    """``upload_to`` callable that replaces the client filename with a UUID."""

    def __init__(self, prefix):
        self.prefix = prefix.strip('/')

    def __call__(self, instance, filename):
        ext = PurePosixPath(filename).suffix.lower()[:8]
        return f'{self.prefix}/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{ext}'

    def __eq__(self, other):
        return isinstance(other, RandomFilename) and other.prefix == self.prefix


def sanitize_image(upload):
    """Validate an uploaded image and return a re-encoded copy without metadata."""
    if upload.size > MAX_IMAGE_BYTES:
        raise ValidationError(f'Images must be smaller than {MAX_IMAGE_BYTES // MB} MB.')
    try:
        upload.seek(0)
        Image.open(upload).verify()
        upload.seek(0)
        img = Image.open(upload)
        fmt = img.format
        if fmt not in ALLOWED_IMAGE_FORMATS:
            raise ValidationError('Unsupported image type. Use JPEG, PNG, WebP or GIF.')
        if fmt == 'GIF':
            # GIF has no EXIF; re-encoding would drop animation frames.
            upload.seek(0)
            return upload
        img.load()
        if fmt == 'JPEG' and img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
        elif img.mode == 'P':
            img = img.convert('RGBA')
        # A fresh image carries pixels only: no EXIF, XMP, ICC text or trailing bytes.
        clean = Image.new(img.mode, img.size)
        clean.paste(img)
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
        raise ValidationError('The uploaded file is not a valid image.')

    buf = io.BytesIO()
    clean.save(buf, format=fmt, **({'quality': 90} if fmt == 'JPEG' else {}))
    ext, content_type = ALLOWED_IMAGE_FORMATS[fmt]
    size = buf.tell()
    buf.seek(0)
    return InMemoryUploadedFile(buf, None, f'image.{ext}', content_type, size, None)


_VIDEO_SIGNATURES = (
    (4, b'ftyp'),              # MP4 / MOV / M4V
    (0, b'\x1a\x45\xdf\xa3'),  # WebM / Matroska
)


def validate_video(upload):
    if upload.size > MAX_VIDEO_BYTES:
        raise ValidationError(f'Videos must be smaller than {MAX_VIDEO_BYTES // MB} MB.')
    upload.seek(0)
    head = upload.read(16)
    upload.seek(0)
    if not any(head[off:off + len(sig)] == sig for off, sig in _VIDEO_SIGNATURES):
        raise ValidationError('Unsupported video type. Use MP4, MOV or WebM.')
    return upload


_EXECUTABLE_SIGNATURES = (b'MZ', b'\x7fELF', b'#!', b'\xca\xfe\xba\xbe', b'\xcf\xfa\xed\xfe')
_BLOCKED_EXTENSIONS = {
    '.exe', '.dll', '.bat', '.cmd', '.sh', '.ps1', '.msi', '.js', '.mjs', '.vbs', '.jar',
    '.apk', '.scr', '.com', '.html', '.htm', '.xhtml', '.svg', '.php', '.py', '.hta', '.lnk',
}


def validate_attachment(upload):
    """Chat attachments: size cap; refuse executables and browser-active content."""
    if upload.size > MAX_FILE_BYTES:
        raise ValidationError(f'Files must be smaller than {MAX_FILE_BYTES // MB} MB.')
    ext = PurePosixPath(upload.name or '').suffix.lower()
    upload.seek(0)
    head = upload.read(8)
    upload.seek(0)
    if ext in _BLOCKED_EXTENSIONS or any(head.startswith(sig) for sig in _EXECUTABLE_SIGNATURES):
        raise ValidationError('This file type is not allowed.')
    return upload
