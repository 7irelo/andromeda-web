"""
Export synthetic conversations for smart-reply fine-tuning (ai/finetune).

    python manage.py export_reply_sft --out conversations.jsonl

Only rooms where every member is a seed account (``@example.test``, made by
``manage.py seed``) and nobody has opted out of AI are exported; a room with
even one real member is skipped entirely. Names are pseudonymised ("Person 1",
"Person 2", ...) in the speaker field and in the message text, and ids are
replaced by positions. Real users' conversations are never read into the
output.

Each line is one conversation:

    {"conversation": 0, "messages": [{"i": 0, "speaker": "Person 1", "text": "..."}],
     "suggestion_sets": [{"viewer": "Person 2", "anchor": 3, "variant": "haiku",
                          "shown": [{"text": "..." | null, "action": "accepted|edited|dismissed|ignored"}]}]}

Suggestion text is only known where it was captured for seed rooms
(REPLY_SFT_CAPTURE_SEED_TEXT); otherwise ``text`` is null.
"""
import json
import re
from collections import defaultdict

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from chats.models import ChatRoom, Message, ReplySuggestionEvent, SeedReplySuggestion
from chats.smart_replies import SEED_EMAIL_SUFFIX, is_seed_room

FINAL_ACTIONS = ('accepted', 'edited', 'dismissed')


def seed_rooms():
    User = get_user_model()
    real = User.objects.exclude(email__iendswith=SEED_EMAIL_SUFFIX)
    return (ChatRoom.objects.exclude(members__in=real).exclude(members__ai_opt_out=True)
            .annotate(n=Count('members', distinct=True)).filter(n__gte=2).order_by('id'))


class Pseudonyms:
    """Per-conversation "Person N" names, also substituted for real names inside the text."""

    def __init__(self, members):
        self.by_id = {}
        self.patterns = []
        for n, user in enumerate(sorted(members, key=lambda u: u.id), start=1):
            alias = f'Person {n}'
            self.by_id[user.id] = alias
            names = {user.username, user.get_full_name(), user.first_name, user.last_name, user.email}
            for name in sorted((x for x in names if x and len(x) > 1), key=len, reverse=True):
                self.patterns.append((re.compile(rf'(?<!\w)@?{re.escape(name)}(?!\w)', re.IGNORECASE), alias))

    def name(self, user_id):
        return self.by_id.get(user_id, 'Someone')

    def scrub(self, text):
        for pattern, alias in self.patterns:
            text = pattern.sub(alias, text)
        return text


def export_room(index, room, texts):
    members = list(room.members.all())
    if not is_seed_room(room):  # defence in depth: re-check every member in Python
        return None
    names = Pseudonyms(members)
    msgs = list(Message.objects.filter(room=room, is_deleted=False).order_by('created_at', 'id'))
    position, out = {}, []
    for m in msgs:
        text = (m.content or m.transcript).strip()
        if not text or m.sender_id is None:
            continue
        position[m.id] = len(out)
        out.append({'i': len(out), 'speaker': names.name(m.sender_id), 'text': names.scrub(text)})
    if len(out) < 2:
        return None

    sets = defaultdict(dict)
    events = ReplySuggestionEvent.objects.filter(room=room).order_by('created_at', 'id')
    for e in events:
        if e.anchor_message_id not in position:
            continue
        key = (e.user_id, e.anchor_message_id, e.variant)
        if e.action == 'shown':
            sets[key].setdefault(e.suggestion_hash, 'ignored')
        elif e.action in FINAL_ACTIONS and e.suggestion_hash in sets[key]:
            sets[key][e.suggestion_hash] = e.action
    suggestion_sets = []
    for (user_id, anchor, variant), shown in sets.items():
        if not shown:
            continue
        suggestion_sets.append({
            'viewer': names.name(user_id), 'anchor': position[anchor], 'variant': variant,
            'shown': [{'text': names.scrub(texts[h]) if h in texts else None, 'action': action}
                      for h, action in shown.items()],
        })
    return {'conversation': index, 'messages': out, 'suggestion_sets': suggestion_sets}


class Command(BaseCommand):
    help = 'Export seed-account conversations (pseudonymised) as JSONL for smart-reply fine-tuning.'

    def add_arguments(self, parser):
        parser.add_argument('--out', required=True, help='Output JSONL path')
        parser.add_argument('--max-rooms', type=int, default=10_000)

    def handle(self, *args, out, max_rooms, **options):
        if not out.endswith('.jsonl'):
            raise CommandError('--out must be a .jsonl file.')
        written = 0
        with open(out, 'w', encoding='utf-8') as fh:
            for room in seed_rooms().prefetch_related('members')[:max_rooms]:
                hashes = ReplySuggestionEvent.objects.filter(room=room).values_list('suggestion_hash', flat=True)
                texts = dict(SeedReplySuggestion.objects.filter(suggestion_hash__in=hashes)
                             .values_list('suggestion_hash', 'text'))
                row = export_room(written, room, texts)
                if row:
                    fh.write(json.dumps(row, ensure_ascii=False) + '\n')
                    written += 1
        self.stdout.write(self.style.SUCCESS(f'Exported {written} seed conversations to {out}'))
