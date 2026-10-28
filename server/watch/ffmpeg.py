"""
ffmpeg / ffprobe wrappers for the video pipeline.

Untrusted media is the risky input here, so:
- every call is an argument list (never a shell) built only from numbers we
  computed and paths inside a temporary directory we created;
- only local files may be opened (``-protocol_whitelist file``) and only the
  MP4/MOV and Matroska/WebM demuxers are allowed, so a crafted upload can't
  smuggle in an HLS or concat playlist that reads other files or the network;
- every call has a timeout and no stdin.
"""
import json
import logging
import shutil
import subprocess  # noqa: S404 - argument lists only, see module docstring
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Demuxer names as ffmpeg reports them in ``format_name``.
ALLOWED_FORMATS = {'mov', 'mp4', 'm4a', '3gp', '3g2', 'mj2', 'matroska', 'webm'}
_INPUT_GUARDS = ['-protocol_whitelist', 'file', '-format_whitelist', 'mov,mp4,matroska,webm']
MAX_DIMENSION = 7680
PROBE_TIMEOUT = 30
STILL_TIMEOUT = 120
AUDIO_TIMEOUT = 300
SPRITE_TILES = 10


class ProcessingError(Exception):
    """A permanent problem with the upload. ``reason`` is shown to the uploader."""

    def __init__(self, reason, detail=''):
        super().__init__(detail or reason)
        self.reason = reason


class ToolMissing(Exception):
    pass


@dataclass
class Probe:
    duration: float
    width: int
    height: int
    has_audio: bool


def _binary(name):
    path = shutil.which(name)
    if not path:
        raise ToolMissing(name)
    return path


def _exec(argv, timeout):
    # The only subprocess call in the app; argv never contains user text.
    return subprocess.run(argv, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,  # noqa: S603
                          check=False)


def run(tool, args, timeout):
    argv = [_binary(tool), *[str(a) for a in args]]
    try:
        proc = _exec(argv, timeout)
    except subprocess.TimeoutExpired:
        raise ProcessingError('Processing this video took too long.', f'{tool} timed out') from None
    if proc.returncode != 0:
        tail = (proc.stderr or b'')[-500:].decode(errors='replace')
        raise ProcessingError("We couldn't process this video.", f'{tool} exited {proc.returncode}: {tail}')
    return proc.stdout or b''


def probe(src):
    out = run('ffprobe', ['-v', 'error', *_INPUT_GUARDS, '-print_format', 'json',
                          '-show_format', '-show_streams', src], PROBE_TIMEOUT)
    try:
        info = json.loads(out)
    except ValueError:
        raise ProcessingError("We couldn't read this video.") from None
    fmt = info.get('format') or {}
    names = set((fmt.get('format_name') or '').split(','))
    if not names & ALLOWED_FORMATS:
        raise ProcessingError('Unsupported video type. Use MP4, MOV or WebM.')
    streams = info.get('streams') or []
    video = next((s for s in streams if s.get('codec_type') == 'video'), None)
    if video is None:
        raise ProcessingError('This file has no video track.')
    try:
        duration = float(fmt.get('duration') or video.get('duration') or 0)
        width, height = int(video.get('width') or 0), int(video.get('height') or 0)
    except (TypeError, ValueError):
        raise ProcessingError("We couldn't read this video.") from None
    if duration <= 0 or not (0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION):
        raise ProcessingError("We couldn't read this video.")
    has_audio = any(s.get('codec_type') == 'audio' for s in streams)
    return Probe(duration, width, height, has_audio)


def _even(n):
    return max(2, int(round(n / 2)) * 2)


def rendition_size(p, target):
    """Output size for a rendition whose short side is ``target`` (never upscaled)."""
    short = min(p.width, p.height)
    t = _even(min(target, short))
    if p.width >= p.height:
        return _even(p.width * t / p.height), t
    return t, _even(p.height * t / p.width)


def renditions_for(p):
    """360p always; 720p only when the source has at least that much to give."""
    return [360, 720] if min(p.width, p.height) >= 720 else [360]


def thumbnail(src, dest, p):
    at = min(p.duration * 0.1, 5.0)
    run('ffmpeg', ['-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-ss', f'{at:.2f}', *_INPUT_GUARDS,
                   '-i', src, '-frames:v', '1', '-vf', 'scale=640:-2', '-q:v', '4', dest], STILL_TIMEOUT)


def sprite(src, dest, p):
    """A strip of SPRITE_TILES small frames. Keyframes only, so it's cheap."""
    rate = SPRITE_TILES / max(p.duration, 1.0)
    vf = f'fps={rate:.6f},scale=160:90:force_original_aspect_ratio=decrease,pad=160:90:-1:-1,tile={SPRITE_TILES}x1'
    run('ffmpeg', ['-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-skip_frame', 'nokey', *_INPUT_GUARDS,
                   '-i', src, '-vf', vf, '-frames:v', '1', '-q:v', '6', dest], STILL_TIMEOUT)


def hls(src, out_dir, p, target):
    """Transcode one H.264/AAC HLS rendition into ``out_dir``. Returns (width, height)."""
    width, height = rendition_size(p, target)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    maxrate, bufsize = {360: ('900k', '1800k'), 720: ('2800k', '5600k')}[target]
    timeout = int(max(600, p.duration * 3))
    run('ffmpeg', [
        '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', *_INPUT_GUARDS, '-i', src,
        '-map', '0:v:0', '-map', '0:a:0?', '-sn', '-dn', '-map_metadata', '-1',
        '-vf', f'scale={width}:{height}', '-fpsmax', '30', '-pix_fmt', 'yuv420p',
        '-c:v', 'libx264', '-preset', 'veryfast', '-profile:v', 'main', '-crf', '23',
        '-maxrate', maxrate, '-bufsize', bufsize,
        '-g', '60', '-keyint_min', '60', '-sc_threshold', '0',
        '-c:a', 'aac', '-b:a', '96k', '-ac', '2', '-ar', '48000',
        '-f', 'hls', '-hls_time', '6', '-hls_playlist_type', 'vod', '-hls_flags', 'independent_segments',
        '-hls_segment_filename', str(out_dir / 'seg_%05d.ts'), str(out_dir / 'index.m3u8'),
    ], timeout)
    return width, height


def master_playlist(variants):
    """``variants``: [(dirname, width, height, bandwidth_bps)] -> master.m3u8 text."""
    lines = ['#EXTM3U', '#EXT-X-VERSION:3', '#EXT-X-INDEPENDENT-SEGMENTS']
    for name, width, height, bandwidth in variants:
        lines += [f'#EXT-X-STREAM-INF:BANDWIDTH={int(bandwidth)},RESOLUTION={width}x{height}', f'{name}/index.m3u8']
    return '\n'.join(lines) + '\n'


def extract_audio(src, dest):
    """Mono 16 kHz Opus in WebM: small, and all speech-to-text needs."""
    run('ffmpeg', ['-nostdin', '-hide_banner', '-loglevel', 'error', '-y', *_INPUT_GUARDS, '-i', src,
                   '-map', '0:a:0', '-vn', '-sn', '-dn', '-map_metadata', '-1', '-ac', '1', '-ar', '16000',
                   '-c:a', 'libopus', '-b:a', '24k', '-application', 'voip', '-f', 'webm', dest], AUDIO_TIMEOUT)
