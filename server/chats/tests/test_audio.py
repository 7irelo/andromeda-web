"""Voice-note sniffing, audio-only enforcement and length limits."""
import json
import subprocess
from unittest import mock

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from chats import audio
from chats.tests.helpers import mp3, mp4, ogg_opus, webm


def upload(data, name='clip.bin'):
    return SimpleUploadedFile(name, data, content_type='audio/webm')


@pytest.mark.parametrize('data, ext, mime, seconds', [
    (webm(12), 'webm', 'audio/webm', 12),
    (webm(12, with_duration=True), 'webm', 'audio/webm', 12),
    (webm(12, codec=b'A_VORBIS'), 'webm', 'audio/webm', 12),
    (ogg_opus(42), 'ogg', 'audio/ogg', 42),
    (mp4(30), 'm4a', 'audio/mp4', 30),
    (mp3(20), 'mp3', 'audio/mpeg', 20),
], ids=['webm', 'webm-duration', 'webm-vorbis', 'ogg', 'mp4', 'mp3'])
def test_accepts_audio_and_reads_length(data, ext, mime, seconds):
    clean, mimetype, duration = audio.validate_voice(upload(data, name='evil.html'))
    assert mimetype == mime
    # The stored name comes from the sniffed type, never from the client.
    assert clean.name == f'voice.{ext}'
    assert duration == pytest.approx(seconds, abs=0.1)


@pytest.mark.parametrize('data', [
    webm(10, codec=b'V_VP8', track_type=1),                                  # video only
    webm(10, extra_tracks=b'\xae\x01\x00\x00\x00\x00\x00\x00\x03\x83\x81\x01'),  # audio + video track
    webm(10, doctype=b'matroska'),
    ogg_opus(10, head=b'\x80theora' + b'\0' * 40),
    mp4(10, handlers=(b'soun', b'vide')),
    mp4(10, handlers=(b'vide',)),
    b'MZ\x90\x00' + b'\0' * 200,
    b'<html><script>alert(1)</script></html>',
    b'',
], ids=['webm-video', 'webm-audio-video', 'matroska', 'ogg-theora', 'mp4-audio-video', 'mp4-video', 'exe', 'html',
        'empty'])
def test_rejects_non_audio(data):
    with pytest.raises(ValidationError):
        audio.validate_voice(upload(data))


def test_rejects_long_recordings():
    for data in (webm(400), ogg_opus(301.5), mp4(600), mp3(320)):
        with pytest.raises(ValidationError, match='minutes'):
            audio.validate_voice(upload(data))


def test_accepts_exactly_five_minutes():
    assert audio.validate_voice(upload(ogg_opus(300)))[2] == pytest.approx(300)


def test_rejects_oversized_files():
    data = ogg_opus(10) + b'\0' * (audio.MAX_VOICE_BYTES)
    with pytest.raises(ValidationError, match='smaller'):
        audio.validate_voice(upload(data))


def test_rejects_truncated_garbage_after_mp3():
    with pytest.raises(ValidationError):
        audio.validate_voice(upload(mp3(5) + b'\x00' * (audio.MP3_TRAILER_SLACK + 10)))


def _probe(stdout, returncode=0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=json.dumps(stdout).encode(), stderr=b'')


class TestFfprobeFallback:
    """Fragmented MP4 without a duration in the header falls back to ffprobe."""

    def test_uses_ffprobe_with_argument_list_and_timeout(self):
        result = _probe({'streams': [{'codec_type': 'audio'}], 'format': {'duration': '61.5'}})
        with mock.patch('chats.audio.shutil.which', return_value='/usr/bin/ffprobe'), \
                mock.patch('chats.audio.subprocess.run', return_value=result) as run:
            _, _, duration = audio.validate_voice(upload(mp4(0, duration=False)))
        assert duration == 61.5
        args, kwargs = run.call_args
        assert isinstance(args[0], list) and args[0][0] == '/usr/bin/ffprobe'
        assert kwargs['timeout'] == audio.FFPROBE_TIMEOUT_S
        assert not kwargs.get('shell')

    def test_ffprobe_too_long(self):
        result = _probe({'streams': [{'codec_type': 'audio'}], 'format': {'duration': '900'}})
        with mock.patch('chats.audio.shutil.which', return_value='/usr/bin/ffprobe'), \
                mock.patch('chats.audio.subprocess.run', return_value=result):
            with pytest.raises(ValidationError, match='minutes'):
                audio.validate_voice(upload(mp4(0, duration=False)))

    def test_ffprobe_finds_video_stream(self):
        result = _probe({'streams': [{'codec_type': 'audio'}, {'codec_type': 'video'}], 'format': {'duration': '5'}})
        with mock.patch('chats.audio.shutil.which', return_value='/usr/bin/ffprobe'), \
                mock.patch('chats.audio.subprocess.run', return_value=result):
            with pytest.raises(ValidationError, match='audio only'):
                audio.validate_voice(upload(mp4(0, duration=False)))

    def test_ffprobe_timeout_rejects(self):
        with mock.patch('chats.audio.shutil.which', return_value='/usr/bin/ffprobe'), \
                mock.patch('chats.audio.subprocess.run', side_effect=subprocess.TimeoutExpired('ffprobe', 10)):
            with pytest.raises(ValidationError, match='length'):
                audio.validate_voice(upload(mp4(0, duration=False)))

    def test_no_ffprobe_and_no_length_rejects(self):
        with mock.patch('chats.audio.shutil.which', return_value=None):
            with pytest.raises(ValidationError, match='length'):
                audio.validate_voice(upload(mp4(0, duration=False)))
