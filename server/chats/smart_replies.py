"""
Smart replies: building the AI request for one room, and logging implicit feedback.

Privacy rules, enforced here rather than trusted to the model:
- only the latest messages of the one room the member is viewing are sent,
  never another room's, and never messages from users they've blocked or
  been blocked by;
- suggestion text is never stored: events carry a keyed hash (HMAC-SHA256
  over the normalised text, keyed from SECRET_KEY so short common replies
  can't be reversed with a dictionary);
- the one exception is synthetic data: with REPLY_SFT_CAPTURE_SEED_TEXT on,
  text is kept for rooms whose members are all seed accounts, so offline
  preference pairs can be built. Seed accounts use the reserved ``.test``
  domain (RFC 6761), which can't receive mail, so a real account can't
  verify such an address.
"""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.crypto import salted_hmac

from core import ai_client, experiments, visibility
from .models import Message, ReplySuggestionEvent, SeedReplySuggestion

EXPERIMENT = 'smart_replies_v1'
DEFAULT_VARIANTS = {'haiku': 50, 'luna': 50}
CONTEXT_MESSAGES = 20
MESSAGE_CHARS = 500
FEEDBACK_WINDOW = timedelta(hours=24)
SEED_EMAIL_SUFFIX = '@example.test'
FEEDBACK_ACTIONS = (ReplySuggestionEvent.ACTION_ACCEPTED, ReplySuggestionEvent.ACTION_EDITED,
                    ReplySuggestionEvent.ACTION_DISMISSED)


def display_name(user):
    if user is None:
        return 'deleted user'
    return (user.get_full_name() or user.username)[:150]


def normalise(text):
    return ' '.join(str(text).split())


def suggestion_hash(text):
    return salted_hmac('chats.reply_suggestion', normalise(text), algorithm='sha256').hexdigest()


def variant_for(user):
    return experiments.bucket(user.id, EXPERIMENT, getattr(settings, 'SMART_REPLY_VARIANTS', DEFAULT_VARIANTS))


def is_seed_user(user):
    return bool(user and user.email and user.email.lower().endswith(SEED_EMAIL_SUFFIX))


def is_seed_room(room):
    members = list(room.members.all())
    return bool(members) and all(is_seed_user(u) and not u.ai_opt_out for u in members)


def context_messages(room, viewer):
    """The room's latest text messages (oldest first), minus blocked users' and AI-opted-out members' messages."""
    qs = (Message.objects.filter(room=room, is_deleted=False)
          .exclude(sender_id__in=visibility.blocked_ids(viewer))
          .exclude(sender__ai_opt_out=True)
          .select_related('sender').order_by('-created_at', '-id'))
    batch = [m for m in qs[:CONTEXT_MESSAGES * 2] if (m.content or m.transcript).strip()][:CONTEXT_MESSAGES]
    batch.reverse()
    return batch


def suggest(room, viewer):
    """Ask the AI service for replies and log what was shown. Raises ai_client errors."""
    variant = variant_for(viewer)
    msgs = context_messages(room, viewer)
    anchor = msgs[-1].id if msgs else None
    if not any(m.sender_id != viewer.id for m in msgs):
        return {'suggestions': [], 'variant': variant, 'anchor_id': anchor}
    payload = {
        'viewer': display_name(viewer),
        'variant': variant,
        'messages': [{'id': m.id, 'sender': display_name(m.sender), 'is_viewer': m.sender_id == viewer.id,
                      'text': (m.content or m.transcript)[:MESSAGE_CHARS]} for m in msgs],
    }
    result = ai_client.call('/v1/replies', payload, user_id=viewer.id)
    texts = [normalise(t)[:120] for t in result.get('suggestions', [])[:3] if isinstance(t, str) and t.strip()]
    suggestions = [{'id': suggestion_hash(t), 'text': t} for t in dict.fromkeys(texts)]
    ReplySuggestionEvent.objects.bulk_create([
        ReplySuggestionEvent(user=viewer, room=room, suggestion_hash=s['id'], action=ReplySuggestionEvent.ACTION_SHOWN,
                             variant=variant, anchor_message_id=anchor)
        for s in suggestions
    ])
    if getattr(settings, 'REPLY_SFT_CAPTURE_SEED_TEXT', False) and suggestions and is_seed_room(room):
        SeedReplySuggestion.objects.bulk_create(
            [SeedReplySuggestion(suggestion_hash=s['id'], text=s['text']) for s in suggestions],
            ignore_conflicts=True,
        )
    return {'suggestions': suggestions, 'variant': variant, 'anchor_id': anchor}


def record_feedback(viewer, room, ids, action):
    """
    Log accepted / edited / dismissed for suggestions this user was shown in
    this room recently. Returns how many events were written; unknown or
    repeated feedback is ignored, so the metrics can't be inflated.
    """
    shown = {}
    recent = ReplySuggestionEvent.objects.filter(
        user=viewer, room=room, action=ReplySuggestionEvent.ACTION_SHOWN, suggestion_hash__in=ids,
        created_at__gte=timezone.now() - FEEDBACK_WINDOW,
    ).order_by('created_at')
    for e in recent:
        shown[e.suggestion_hash] = e  # the latest showing wins
    if not shown:
        return None
    answered = set(ReplySuggestionEvent.objects.filter(
        user=viewer, room=room, suggestion_hash__in=list(shown), action__in=FEEDBACK_ACTIONS,
    ).values_list('suggestion_hash', 'anchor_message_id'))
    events = [ReplySuggestionEvent(user=viewer, room=room, suggestion_hash=h, action=action, variant=e.variant,
                                   anchor_message_id=e.anchor_message_id)
              for h, e in shown.items() if (h, e.anchor_message_id) not in answered]
    ReplySuggestionEvent.objects.bulk_create(events)
    return len(events)
