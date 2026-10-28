"""Shared fixtures-as-functions for the chat tests: users, rooms, a WebSocket driver and audio samples."""
import json
import struct

from asgiref.testing import ApplicationCommunicator
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from chats.consumers import ChatConsumer
from chats.models import ChatMember, ChatRoom

User = get_user_model()
PASSWORD = 'correct-horse-battery'


def make_user(name, **extra):
    return User.objects.create_user(username=name, email=f'{name}@example.com', password=PASSWORD, **extra)


def client_for(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def make_room(admin, *members, room_type='group', name='Crew'):
    room = ChatRoom.objects.create(room_type=room_type, name=name if room_type == 'group' else '', created_by=admin)
    ChatMember.objects.create(room=room, user=admin, role='admin')
    for m in members:
        ChatMember.objects.create(room=room, user=m)
    return room


class WS:
    """Minimal WebSocket test client (channels.testing needs daphne, which isn't installed)."""

    def __init__(self, user, room_id):
        scope = {
            'type': 'websocket', 'path': f'/ws/chat/{room_id}/', 'query_string': b'', 'headers': [],
            'subprotocols': [], 'user': user, 'url_route': {'kwargs': {'room_id': str(room_id)}},
        }
        self.comm = ApplicationCommunicator(ChatConsumer.as_asgi(), scope)

    async def connect(self):
        await self.comm.send_input({'type': 'websocket.connect'})
        out = await self.comm.receive_output(2)
        return out['type'] == 'websocket.accept', out.get('code')

    async def send(self, data):
        await self.comm.send_input({'type': 'websocket.receive', 'text': data if isinstance(data, str) else json.dumps(data)})

    async def receive(self, timeout=2):
        out = await self.comm.receive_output(timeout)
        if out['type'] == 'websocket.close':
            return {'type': '__closed__', 'code': out.get('code')}
        return json.loads(out['text'])

    async def receive_type(self, kind, timeout=2):
        """Skip unrelated frames (presence, status) until one of ``kind`` arrives."""
        for _ in range(20):
            frame = await self.receive(timeout)
            if frame['type'] in (kind, '__closed__'):
                return frame
        raise AssertionError(f'no {kind} frame')

    async def nothing(self, timeout=0.2):
        return await self.comm.receive_nothing(timeout)

    async def drain(self):
        while not await self.comm.receive_nothing(0.05):
            await self.comm.receive_output(0.1)

    async def close(self):
        await self.comm.send_input({'type': 'websocket.disconnect', 'code': 1000})
        try:
            await self.comm.wait(1)
        except Exception:  # noqa: S110 - the consumer may already have finished
            pass


# ── Audio samples ─────────────────────────────────────────────────────────────

def _ebml_id(i):
    return i.to_bytes((i.bit_length() + 7) // 8, 'big')


def _el(i, payload):
    return _ebml_id(i) + b'\x01' + len(payload).to_bytes(7, 'big') + payload


_UNKNOWN = b'\x01\xff\xff\xff\xff\xff\xff\xff'


def webm(seconds, codec=b'A_OPUS', track_type=2, doctype=b'webm', with_duration=False, extra_tracks=b''):
    """Streaming-style WebM like MediaRecorder writes: unknown-size Segment/Clusters, no Duration."""
    header = _el(0x1A45DFA3, _el(0x4282, doctype))
    info = _el(0x1549A966, _el(0x2AD7B1, (1_000_000).to_bytes(3, 'big'))
               + (_el(0x4489, struct.pack('>d', seconds * 1000)) if with_duration else b''))
    tracks = _el(0x1654AE6B, _el(0xAE, _el(0x83, bytes([track_type])) + _el(0x86, codec)) + extra_tracks)
    ms = int(seconds * 1000)
    clusters = b''
    for start in range(0, ms + 1, 10_000):
        blocks = b''.join(_el(0xA3, b'\x81' + struct.pack('>h', rel) + b'\x80' + b'\x00' * 10)
                          for rel in range(0, min(10_000, ms - start + 1), 1000))
        clusters += _ebml_id(0x1F43B675) + _UNKNOWN + _el(0xE7, start.to_bytes(4, 'big')) + blocks
    return header + _ebml_id(0x18538067) + _UNKNOWN + info + tracks + clusters


def _ogg_page(payload, granule, serial=1, bos=False, seq=0):
    segs, n = [], len(payload)
    while n >= 255:
        segs.append(255)
        n -= 255
    segs.append(n)
    return (b'OggS' + bytes([0, 0x02 if bos else 0]) + struct.pack('<qII', granule, serial, seq)
            + b'\0\0\0\0' + bytes([len(segs)]) + bytes(segs) + payload)


def ogg_opus(seconds, head=None):
    head = head or (b'OpusHead' + bytes([1, 1]) + struct.pack('<HI', 312, 48000) + b'\0\0\0')
    return (_ogg_page(head, 0, bos=True) + _ogg_page(b'OpusTags' + b'\0' * 8, 0, seq=1)
            + _ogg_page(b'\0' * 50, int(seconds * 48000) + 312, seq=2))


def _box(kind, body):
    return struct.pack('>I', 8 + len(body)) + kind + body


def mp4(seconds, handlers=(b'soun',), duration=True):
    mvhd = _box(b'mvhd', b'\0' * 4 + struct.pack('>IIII', 0, 0, 1000, int(seconds * 1000) if duration else 0)
                + b'\0' * 80)
    traks = b''.join(_box(b'trak', _box(b'mdia', _box(b'hdlr', b'\0' * 8 + h + b'\0' * 12))) for h in handlers)
    return _box(b'ftyp', b'M4A \0\0\0\0') + _box(b'moov', mvhd + traks) + _box(b'mdat', b'\0' * 100)


def mp3(seconds):
    """MPEG-1 Layer III, 128 kbps, 44.1 kHz, constant bitrate."""
    frame = b'\xff\xfb\x90\x00' + b'\0' * 413
    frames = int(seconds * 44100 / 1152) + 1
    return b'ID3\x03\x00\x00\x00\x00\x00\x00' + frame * frames
