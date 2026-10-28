"""
Data rights: export, delayed deletion and erasure.

- Export builds a zip of everything the member has here: their profile and
  settings, what they posted, sent, listed and reviewed, their connections,
  notifications, consents and sign-in devices, the moderation decisions about
  them, and the files they uploaded (up to a size cap). It's stored under the
  private prefix, downloadable only by its owner, and deleted after 7 days.
- Deletion is delayed by a grace period. The account is signed out and
  locked straight away; signing in again within the period cancels it.
- Erasure deletes the account row, which cascades to everything they own.
  File cleanup (core.media_cleanup), the search index (retrieval signals) and
  the graph node (users.signals) all follow from those deletes.
"""
import io
import json
import zipfile
from datetime import timedelta

from django.core.files.base import ContentFile
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q
from django.utils import timezone

EXPORT_TTL = timedelta(days=7)
DELETION_GRACE = timedelta(days=14)
MAX_EXPORT_MEDIA_BYTES = 500 * 1024 * 1024


def _rows(qs, fields):
    return [{f: getattr(o, f) for f in fields} for o in qs]


def collect(user):
    """Everything about `user`, as JSON-able dicts, plus the files to include."""
    from chats.models import Message, ReplySuggestionEvent
    from groups.models import GroupMember
    from marketplace.models import Listing, ListingImage, Review
    from moderation.models import ModerationCase, Report
    from notifications.models import Notification
    from pages.models import PageFollow
    from posts.models import Comment, Like, Post, PostMedia

    from .models import Block, ConsentRecord, FriendRequest, UserSession

    profile_fields = ['id', 'username', 'email', 'first_name', 'last_name', 'bio', 'location', 'website',
                      'birth_date', 'date_joined', 'last_login', 'email_verified', 'ai_opt_out', 'privacy_profile',
                      'privacy_messages', 'privacy_friend_requests', 'privacy_friends_list', 'default_post_privacy',
                      'show_online_status', 'searchable']
    posts = Post.objects.filter(author=user)
    data = {
        'profile': {f: getattr(user, f) for f in profile_fields},
        'posts': _rows(posts, ['id', 'content', 'privacy', 'group_id', 'page_id', 'link_url', 'created_at',
                               'updated_at']),
        'comments': _rows(Comment.objects.filter(author=user), ['id', 'post_id', 'parent_id', 'content', 'created_at']),
        'reactions': _rows(Like.objects.filter(user=user), ['post_id', 'reaction', 'created_at']),
        'messages_sent': _rows(Message.objects.filter(sender=user, is_deleted=False),
                               ['id', 'room_id', 'content', 'message_type', 'created_at']),
        'listings': _rows(Listing.objects.filter(seller=user), ['id', 'title', 'description', 'price', 'currency',
                                                                 'condition', 'status', 'location', 'created_at']),
        'reviews_written': _rows(Review.objects.filter(reviewer=user), ['listing_id', 'rating', 'comment',
                                                                         'created_at']),
        'friend_requests': _rows(FriendRequest.objects.filter(Q(sender=user) | Q(receiver=user)),
                                 ['sender_id', 'receiver_id', 'status', 'created_at']),
        'blocked_users': list(Block.objects.filter(blocker=user).values_list('blocked_id', flat=True)),
        'group_memberships': _rows(GroupMember.objects.filter(user=user), ['group_id', 'role', 'joined_at']),
        'pages_followed': list(PageFollow.objects.filter(user=user).values_list('page_id', flat=True)),
        'notifications': _rows(Notification.objects.filter(recipient=user)[:5000],
                               ['notification_type', 'title', 'body', 'is_read', 'created_at']),
        'smart_reply_feedback': _rows(ReplySuggestionEvent.objects.filter(user=user),
                                      ['room_id', 'action', 'variant', 'created_at']),
        'consents': _rows(ConsentRecord.objects.filter(user=user), ['kind', 'version', 'granted', 'created_at']),
        'sign_in_devices': _rows(UserSession.objects.filter(user=user),
                                 ['user_agent', 'ip_prefix', 'created_at', 'last_seen_at', 'revoked_at']),
        'moderation_decisions': _rows(ModerationCase.objects.filter(author=user),
                                      ['content_type', 'object_id', 'decision', 'categories', 'reason', 'created_at']),
        'reports_made': _rows(Report.objects.filter(reporter=user),
                              ['content_type', 'object_id', 'reason', 'status', 'created_at']),
    }
    files = []
    for f in (user.avatar, user.cover_photo):
        if f:
            files.append(('profile', f))
    for p in posts:
        if p.image:
            files.append((f'posts/{p.id}', p.image))
    for m in PostMedia.objects.filter(post__author=user):
        files.append((f'posts/{m.post_id}', m.file))
    for img in ListingImage.objects.filter(listing__seller=user):
        files.append((f'listings/{img.listing_id}', img.image))
    for msg in Message.objects.filter(sender=user, is_deleted=False).exclude(file=''):
        if msg.file:
            files.append((f'messages/{msg.room_id}', msg.file))
    return data, files


def build_export(user):
    data, files = collect(user)
    buf = io.BytesIO()
    included, skipped, total = [], [], 0
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, value in data.items():
            z.writestr(f'{name}.json', json.dumps(value, cls=DjangoJSONEncoder, indent=2, ensure_ascii=False))
        for folder, f in files:
            try:
                size = f.size
                if total + size > MAX_EXPORT_MEDIA_BYTES:
                    skipped.append(f.name)
                    continue
                with f.open('rb') as fh:
                    z.writestr(f'files/{folder}/{f.name.rsplit("/", 1)[-1]}', fh.read())
                total += size
                included.append(f.name)
            except Exception:
                skipped.append(f.name)
        z.writestr('README.txt', 'Your Andromeda data export.\n\nEach .json file holds one kind of data. '
                   'Files you uploaded are under files/.\n'
                   + (f'{len(skipped)} file(s) were left out because of the size limit or because they '
                      'could not be read. Ask support if you need them.\n' if skipped else ''))
    return buf.getvalue()


def run_export(export):
    from .models import DataExport
    try:
        content = build_export(export.user)
        export.file.save('export.zip', ContentFile(content), save=False)
        export.size_bytes = len(content)
        export.status = DataExport.STATUS_READY
        export.expires_at = timezone.now() + EXPORT_TTL
    except Exception:
        export.status = DataExport.STATUS_FAILED
        raise
    finally:
        export.save()


def schedule_deletion(user):
    from .views import _revoke_all_sessions
    user.deletion_scheduled_at = timezone.now() + DELETION_GRACE
    user.save(update_fields=['deletion_scheduled_at'])
    _revoke_all_sessions(user)


def erase(user):
    """Permanently delete the account and everything that cascades from it."""
    user.delete()
