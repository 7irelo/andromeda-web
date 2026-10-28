"""
Voice-note validation.

Content is sniffed, never trusted from the filename or the client's content
type: only audio-only WebM (Opus/Vorbis), Ogg (Opus/Vorbis), MP4 and MPEG
Layer III are accepted, and any video track is refused. The length is read
from the container itself, or from ffprobe when the container doesn't record
it, so a 10 MB file can't smuggle in hours of low-bitrate audio. Stored
filenames get an extension derived from the sniffed type.
"""
import io
import json
import os
import shutil
import struct
import subprocess  # only ever runs ffprobe, with an argument list and a timeout
import tempfile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import InMemoryUploadedFile

MB = 1024 * 1024
MAX_VOICE_BYTES = 10 * MB
MAX_VOICE_SECONDS = 5 * 60
DURATION_SLACK_S = 1.0
FFPROBE_TIMEOUT_S = 10

# Sniffed container -> (stored extension, mimetype).
FORMATS = {
    'webm': ('webm', 'audio/webm'),
    'ogg': ('ogg', 'audio/ogg'),
    'mp4': ('m4a', 'audio/mp4'),
    'mpeg': ('mp3', 'audio/mpeg'),
}
MIMETYPE_BY_EXT = {f'.{ext}': mime for ext, mime in FORMATS.values()}


class _Invalid(Exception):
    pass


def validate_voice(upload):
    """Return ``(clean_upload, mimetype, duration_s)`` or raise ``ValidationError``."""
    if upload.size > MAX_VOICE_BYTES:
        raise ValidationError(f'Voice notes must be smaller than {MAX_VOICE_BYTES // MB} MB.')
    upload.seek(0)
    data = upload.read(MAX_VOICE_BYTES + 1)
    upload.seek(0)
    if not data or len(data) > MAX_VOICE_BYTES:
        raise ValidationError('The voice note is empty or too large.')

    kind = sniff(data)
    if kind is None:
        raise ValidationError('Unsupported audio type. Record WebM, Ogg, MP4 or MP3 audio.')
    ext, mimetype = FORMATS[kind]
    try:
        duration = PARSERS[kind](data)
    except (_Invalid, struct.error, IndexError, ValueError):
        raise ValidationError('The voice note is not a valid audio recording.') from None
    if duration is None:
        duration = ffprobe_duration(data, f'.{ext}')
    if duration is None:
        raise ValidationError("Couldn't read the length of this recording.")
    if duration <= 0:
        raise ValidationError('The voice note is empty.')
    if duration > MAX_VOICE_SECONDS + DURATION_SLACK_S:
        raise ValidationError(f'Voice notes are limited to {MAX_VOICE_SECONDS // 60} minutes.')

    clean = InMemoryUploadedFile(io.BytesIO(data), None, f'voice.{ext}', mimetype, len(data), None)
    return clean, mimetype, round(duration, 2)


def sniff(data):
    if data[:4] == b'\x1a\x45\xdf\xa3':
        return 'webm'
    if data[:4] == b'OggS':
        return 'ogg'
    if data[4:8] == b'ftyp':
        return 'mp4'
    if data[:3] == b'ID3' or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return 'mpeg'
    return None


# ── WebM (EBML) ───────────────────────────────────────────────────────────────

_EBML_HEADER, _DOCTYPE = 0x1A45DFA3, 0x4282
_SEGMENT, _INFO, _TRACKS, _TRACK_ENTRY = 0x18538067, 0x1549A966, 0x1654AE6B, 0xAE
_CLUSTER, _BLOCK_GROUP = 0x1F43B675, 0xA0
_TIMECODE_SCALE, _DURATION, _TRACK_TYPE, _CODEC_ID = 0x2AD7B1, 0x4489, 0x83, 0x86
_CLUSTER_TIMECODE, _SIMPLE_BLOCK, _BLOCK = 0xE7, 0xA3, 0xA1
# Masters are walked into rather than skipped. Browsers stream WebM with
# unknown-size Segment and Cluster elements, so the walk is flat.
_MASTERS = {_EBML_HEADER, _SEGMENT, _INFO, _TRACKS, _TRACK_ENTRY, _CLUSTER, _BLOCK_GROUP}
_AUDIO_CODECS = {'A_OPUS', 'A_VORBIS'}


def _vint(data, pos, keep_marker):
    first = data[pos]
    length = 1
    while length <= 8 and not first & (0x80 >> (length - 1)):
        length += 1
    if length > 8:
        raise _Invalid('bad vint')
    value = first if keep_marker else first & (0xFF >> length)
    for b in data[pos + 1:pos + length]:
        value = (value << 8) | b
    if pos + length > len(data):
        raise _Invalid('truncated vint')
    unknown = not keep_marker and value == (1 << (7 * length)) - 1
    return value, pos + length, unknown


def parse_webm(data):
    doctype = None
    scale = 1_000_000
    duration = None
    codecs, track_types = [], []
    cluster_tc = 0
    last_tc = 0
    pos = 0
    while pos < len(data):
        el, pos, _ = _vint(data, pos, keep_marker=True)
        size, pos, unknown = _vint(data, pos, keep_marker=False)
        if el in _MASTERS:
            continue
        if unknown:
            raise _Invalid('unknown-size leaf element')
        payload = data[pos:pos + size]
        pos += size
        if el == _DOCTYPE:
            doctype = payload.rstrip(b'\x00').decode('ascii', 'replace')
        elif el == _TIMECODE_SCALE:
            scale = int.from_bytes(payload, 'big') or scale
        elif el == _DURATION and len(payload) in (4, 8):
            duration = struct.unpack('>f' if len(payload) == 4 else '>d', payload)[0]
        elif el == _TRACK_TYPE:
            track_types.append(int.from_bytes(payload, 'big'))
        elif el == _CODEC_ID:
            codecs.append(payload.rstrip(b'\x00').decode('ascii', 'replace'))
        elif el == _CLUSTER_TIMECODE:
            cluster_tc = int.from_bytes(payload, 'big')
        elif el in (_SIMPLE_BLOCK, _BLOCK) and len(payload) >= 4:
            _, off, _ = _vint(payload, 0, keep_marker=False)
            rel = struct.unpack('>h', payload[off:off + 2])[0]
            last_tc = max(last_tc, cluster_tc + rel)
    if doctype != 'webm':
        raise _Invalid('not webm')
    if not codecs or any(c not in _AUDIO_CODECS for c in codecs) or any(t != 2 for t in track_types):
        raise _Invalid('not audio-only')
    if duration and duration > 0:
        return duration * scale / 1e9
    # MediaRecorder doesn't write a Duration: use the last block's timestamp.
    return last_tc * scale / 1e9 if last_tc else None


# ── Ogg ───────────────────────────────────────────────────────────────────────

def parse_ogg(data):
    streams = {}
    pos = 0
    while pos + 27 <= len(data):
        if data[pos:pos + 4] != b'OggS':
            raise _Invalid('lost page sync')
        header_type = data[pos + 5]
        granule, serial = struct.unpack('<qI', data[pos + 6:pos + 18])
        nsegs = data[pos + 26]
        seg_table = data[pos + 27:pos + 27 + nsegs]
        body = pos + 27 + nsegs
        body_len = sum(seg_table)
        payload = data[body:body + body_len]
        if header_type & 0x02:  # beginning of stream: identifies the codec
            if streams:
                raise _Invalid('more than one stream')
            if payload.startswith(b'OpusHead') and len(payload) >= 12:
                streams[serial] = {'rate': 48000, 'skip': struct.unpack('<H', payload[10:12])[0], 'granule': 0}
            elif payload.startswith(b'\x01vorbis') and len(payload) >= 16:
                streams[serial] = {'rate': struct.unpack('<I', payload[12:16])[0], 'skip': 0, 'granule': 0}
            else:
                raise _Invalid('not opus or vorbis')
        elif serial not in streams:
            raise _Invalid('page for unknown stream')
        if granule >= 0:
            streams[serial]['granule'] = max(streams[serial]['granule'], granule)
        pos = body + body_len
    if not streams:
        raise _Invalid('no stream')
    s = next(iter(streams.values()))
    if not s['rate']:
        raise _Invalid('bad sample rate')
    return max(s['granule'] - s['skip'], 0) / s['rate'] or None


# ── MP4 ───────────────────────────────────────────────────────────────────────

_MP4_CONTAINERS = {b'moov', b'trak', b'mdia', b'mvex'}


def parse_mp4(data):
    handlers = []
    timescale = duration = fragment_duration = None

    def walk(start, end):
        nonlocal timescale, duration, fragment_duration
        pos = start
        while pos + 8 <= end:
            size, kind = struct.unpack('>I4s', data[pos:pos + 8])
            header = 8
            if size == 1:
                size = struct.unpack('>Q', data[pos + 8:pos + 16])[0]
                header = 16
            elif size == 0:
                size = end - pos
            if size < header or pos + size > end:
                raise _Invalid('bad box size')
            body = data[pos + header:pos + size]
            if kind in _MP4_CONTAINERS:
                walk(pos + header, pos + size)
            elif kind == b'mvhd':
                if body[0] == 1:
                    timescale, duration = struct.unpack('>IQ', body[20:32])
                else:
                    timescale, duration = struct.unpack('>II', body[12:20])
            elif kind == b'mehd':
                fragment_duration = struct.unpack('>Q' if body[0] == 1 else '>I',
                                                  body[4:12] if body[0] == 1 else body[4:8])[0]
            elif kind == b'hdlr':
                handlers.append(body[8:12])
            pos += size

    walk(0, len(data))
    if b'soun' not in handlers or b'vide' in handlers:
        raise _Invalid('not audio-only')
    if not timescale:
        return None
    length = duration or fragment_duration
    return length / timescale if length else None


# ── MPEG audio (MP3) ──────────────────────────────────────────────────────────

_MP3_BITRATES = {
    1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
    2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
}
_MP3_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}
MP3_TRAILER_SLACK = 4096  # ID3v1 / APE tags after the last frame


def parse_mpeg(data):
    pos = 0
    if data[:3] == b'ID3':
        size = 0
        for b in data[6:10]:
            size = (size << 7) | (b & 0x7F)
        pos = 10 + size + (10 if data[5] & 0x10 else 0)
    frames = seconds = 0.0
    while pos + 4 <= len(data):
        b1, b2 = data[pos + 1], data[pos + 2]
        version, layer = (b1 >> 3) & 3, (b1 >> 1) & 3
        bitrate_idx, rate_idx = b2 >> 4, (b2 >> 2) & 3
        if data[pos] != 0xFF or b1 & 0xE0 != 0xE0 or version == 1 or layer != 1 \
                or bitrate_idx in (0, 15) or rate_idx == 3:
            break
        rate = _MP3_RATES[version][rate_idx]
        bitrate = _MP3_BITRATES[1 if version == 3 else 2][bitrate_idx] * 1000
        samples = 1152 if version == 3 else 576
        length = samples // 8 * bitrate // rate + ((b2 >> 1) & 1)
        frames += 1
        seconds += samples / rate
        pos += length
    if not frames or len(data) - pos > MP3_TRAILER_SLACK:
        raise _Invalid('not a clean mp3 stream')
    return seconds


PARSERS = {'webm': parse_webm, 'ogg': parse_ogg, 'mp4': parse_mp4, 'mpeg': parse_mpeg}


# ── ffprobe fallback ──────────────────────────────────────────────────────────

def ffprobe_duration(data, suffix):
    """Length in seconds via ffprobe, when it's installed. Refuses files with non-audio streams."""
    exe = shutil.which('ffprobe')
    if not exe:
        return None
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, 'wb') as fh:
            fh.write(data)
        result = subprocess.run(  # noqa: S603 - fixed argument list, no shell, bounded runtime
            [exe, '-v', 'error', '-show_entries', 'format=duration:stream=codec_type', '-of', 'json', path],
            capture_output=True, timeout=FFPROBE_TIMEOUT_S, check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    if result.returncode != 0:
        return None
    try:
        info = json.loads(result.stdout or b'{}')
        streams = info.get('streams') or []
        if not streams or any(s.get('codec_type') != 'audio' for s in streams):
            raise ValidationError('Voice notes must contain audio only.')
        return float(info.get('format', {}).get('duration'))
    except (TypeError, ValueError, AttributeError):
        return None
