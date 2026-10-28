"""
Assistant tools, shared by the agent loop and the MCP endpoint.

Security properties every tool keeps, whatever the model asks for:

- The acting user is the run's owner (or the access token's owner). No tool
  takes a user to act as; unknown arguments are rejected.
- Reads go through ``core.visibility`` and the same querysets the feature
  endpoints use. Something the viewer can't see is "Not found.", exactly
  like something that doesn't exist.
- Write tools (``create_post``, ``send_message``) never write. They validate,
  then create a ``Proposal`` the owner approves in the app; approval
  re-validates everything with the permissions in force at that moment.
- Descriptions and schemas are static strings defined here, never built
  from data, so content can't rewrite what a tool claims to do.
- Results are short, model-readable JSON; errors say what to fix.
"""
import json
import re
from dataclasses import dataclass, field

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from core import ai_client, visibility

from .models import PersonalAccessToken, Proposal

NOT_FOUND = 'Not found.'
RESULT_CHARS = 6000
MAX_TEXT = 5000
MAX_PENDING_PROPOSALS = 20
NEAR_ME_KM = 50
KINDS = ['posts', 'listings', 'groups', 'pages', 'videos']
LINKS = {'posts': '/posts/{id}', 'listings': '/marketplace/{id}', 'groups': '/groups/{id}',
         'pages': '/pages/{id}', 'videos': '/watch/{id}'}
_URL_RE = re.compile(r'https?://[^\s<>"\')\]]+', re.IGNORECASE)


class ToolError(Exception):
    """A failure the model can read and act on."""


@dataclass
class Context:
    user: object
    run: object = None
    call_id: str = ''
    source: str = Proposal.SOURCE_ASSISTANT
    token: PersonalAccessToken | None = None
    scopes: tuple | None = None  # None: in-app assistant, every tool
    model: str = ''
    prompt_version: str = ''


@dataclass
class Outcome:
    content: str
    is_error: bool = False
    citations: list = field(default_factory=list)
    proposal: Proposal | None = None


def _dump(data):
    return json.dumps(data, ensure_ascii=False, default=str)[:RESULT_CHARS]


def _cite(kind, obj_id, title):
    return {'id': f'{kind}:{obj_id}', 'type': kind, 'title': (title or kind.rstrip('s').title())[:120],
            'url': LINKS[kind].format(id=obj_id)}


class Args(serializers.Serializer):
    """Tool arguments. Unknown keys are an error, so 'author_id' or 'as_user' can't slip through."""

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError({'non_field_errors': ['Arguments must be a JSON object.']})
        unknown = sorted(set(data) - set(self.fields))
        if unknown:
            raise serializers.ValidationError({k: ['Unknown argument.'] for k in unknown})
        return super().to_internal_value(data)


def _errors(errors):
    parts = []
    for key, msgs in errors.items():
        msgs = msgs if isinstance(msgs, list) else [msgs]
        parts.append(f'{key}: {" ".join(str(m) for m in msgs)}')
    return 'Invalid arguments. ' + '; '.join(parts)


# ── Argument schemas ─────────────────────────────────────────────────────────

class SearchArgs(Args):
    query = serializers.CharField(min_length=2, max_length=200)
    types = serializers.ListField(child=serializers.ChoiceField(choices=KINDS), required=False, max_length=5)


class IdArgs(Args):
    id = serializers.IntegerField(min_value=1)


class NoArgs(Args):
    pass


class PeopleArgs(Args):
    query = serializers.CharField(min_length=2, max_length=100)


class ListingArgs(Args):
    query = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
    max_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False)
    near_me = serializers.BooleanField(required=False, default=False)


class RoomArgs(Args):
    room_id = serializers.IntegerField(min_value=1)


class PostArgs(Args):
    text = serializers.CharField(max_length=MAX_TEXT)
    group_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    privacy = serializers.ChoiceField(choices=['public', 'friends', 'private'], required=False, default='public')


class MessageArgs(Args):
    to_user_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    room_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    text = serializers.CharField(max_length=MAX_TEXT)

    def validate(self, attrs):
        if bool(attrs.get('to_user_id')) == bool(attrs.get('room_id')):
            raise serializers.ValidationError({'to_user_id': ['Give exactly one of to_user_id or room_id.']})
        return attrs


def _obj(props, required=()):
    return {'type': 'object', 'properties': props, 'required': list(required), 'additionalProperties': False}


_STR = {'type': 'string'}
_INT = {'type': 'integer', 'minimum': 1}
_TEXT = {'type': 'string', 'maxLength': MAX_TEXT}


# ── Read tools ───────────────────────────────────────────────────────────────

def search_content(ctx, args):
    from retrieval import documents, hybrid
    _, hits = hybrid.search(ctx.user, args['query'], args.get('types') or KINDS, limit=8)
    items, cites = [], []
    for h in hits:
        doc = documents.load(h.kind, h.id)
        if doc is None:  # gone, removed, or its author opted out of AI features
            continue
        cite = _cite(h.kind, h.id, doc.title)
        cites.append(cite)
        items.append({'id': cite['id'], 'title': cite['title'], 'author': doc.author,
                      'date': doc.created_at[:10], 'text': doc.text[:600]})
    return Outcome(_dump({'results': items} if items else {'results': [], 'note': 'Nothing found.'}), citations=cites)


def get_post(ctx, args):
    post = visibility.visible_posts(ctx.user).select_related('author', 'group').filter(pk=args['id']).first()
    if post is None:
        raise ToolError(NOT_FOUND)
    if post.author.ai_opt_out and post.author_id != ctx.user.id:
        raise ToolError("This post's author has turned off AI features, so it can't be read here.")
    data = {'id': f'posts:{post.id}', 'author': post.author.username, 'date': post.created_at.date().isoformat(),
            'group': post.group.name if post.group_id else None, 'text': post.content[:3000],
            'link_title': post.link_title or None, 'likes': post.likes_count, 'comments': post.comments_count}
    return Outcome(_dump(data), citations=[_cite('posts', post.id, post.content.split('\n')[0])])


def list_my_groups(ctx, args):
    from groups.models import GroupMember
    rows = GroupMember.objects.filter(user=ctx.user).select_related('group').order_by('group__name')[:50]
    groups = [{'id': m.group_id, 'name': m.group.name, 'privacy': m.group.privacy, 'role': m.role} for m in rows]
    return Outcome(_dump({'groups': groups}))


def list_my_chats(ctx, args):
    from chats.models import ChatRoom
    rooms = ChatRoom.objects.filter(members=ctx.user).prefetch_related('members').order_by('-updated_at')[:30]
    blocked = visibility.blocked_ids(ctx.user)
    out = []
    for r in rooms:
        others = [u.username for u in r.members.all() if u.id != ctx.user.id and u.id not in blocked]
        out.append({'room_id': r.id, 'name': r.name or None, 'type': r.room_type, 'with': others[:10]})
    return Outcome(_dump({'chats': out}))


def find_people(ctx, args):
    from core.search import _people
    users = _people(ctx.user, args['query']).exclude(id=ctx.user.id).distinct()[:10]
    people = [{'id': u.id, 'username': u.username, 'name': u.get_full_name() or None,
               'can_message': visibility.can_message(ctx.user, u)} for u in users]
    return Outcome(_dump({'people': people}))


def search_listings(ctx, args):
    from core.search import _text_filter, visible_listings
    from marketplace import geo
    qs = visible_listings(ctx.user).exclude(seller__ai_opt_out=True).select_related('seller')
    if args.get('query'):
        qs = _text_filter(qs, ['title', 'description'], args['query'])
    if args.get('max_price') is not None:
        qs = qs.filter(price__lte=args['max_price'])
    if args.get('near_me'):
        point = geo.centroid_for(ctx.user.location)
        if point is None:
            raise ToolError('Your profile has no city we recognise, so "near me" can\'t be used. Search without it.')
        min_lat, max_lat, min_lng, max_lng = geo.bounding_box(*point, NEAR_ME_KM)
        qs = qs.filter(latitude__range=(min_lat, max_lat), longitude__range=(min_lng, max_lng)).annotate(
            distance=geo.distance_expression(*point)).filter(distance__lte=NEAR_ME_KM)
    rows = list(qs[:10])
    items = [{'id': f'listings:{x.id}', 'title': x.title, 'price': f'{x.currency} {x.price}',
              'location': x.location or None, 'condition': x.get_condition_display(), 'seller': x.seller.username}
             for x in rows]
    return Outcome(_dump({'listings': items} if items else {'listings': [], 'note': 'Nothing found.'}),
                   citations=[_cite('listings', x.id, x.title) for x in rows])


CATCH_UP_MAX_MESSAGES = 300


def summarise_thread(ctx, args):
    """The same summary as "Catch me up" in the chat window, for a room the viewer is in."""
    from chats.models import ChatMember
    member = ChatMember.objects.select_related('room').filter(room_id=args['room_id'], user=ctx.user).first()
    if member is None:
        raise ToolError(NOT_FOUND)
    if ctx.user.ai_opt_out:
        raise ToolError('You have turned off AI features in your settings.')
    room = member.room
    msgs = room.messages.filter(is_deleted=False).exclude(
        sender_id__in=visibility.blocked_ids(ctx.user)).select_related('sender').order_by('-created_at')
    unread = msgs.filter(created_at__gt=member.last_read_at) if member.last_read_at else msgs
    batch = list(unread[:CATCH_UP_MAX_MESSAGES])
    if len(batch) < 3:
        batch = list(msgs[:50])
    batch.reverse()
    payload = {'room_name': room.name, 'viewer': ctx.user.username,
               'messages': [{'id': m.id, 'sender': m.sender.username if m.sender else 'deleted user',
                             'text': (m.content or m.transcript)[:2000], 'sent_at': m.created_at.isoformat()}
                            for m in batch if m.content or m.transcript]}
    if not payload['messages']:
        return Outcome(_dump({'room_id': room.id, 'summary': 'There are no messages to summarise.'}))
    try:
        res = ai_client.call('/v1/catchup', payload, user_id=ctx.user.id)
    except ai_client.AIRejected as exc:
        raise ToolError(str(exc.detail)) from None
    except ai_client.AIUnavailable:
        raise ToolError('Summaries are unavailable right now.') from None
    s = res.get('summary', {})
    data = {'room_id': room.id, 'room': room.name or None, 'tldr': s.get('tldr', ''),
            'topics': [{'title': t.get('title'), 'summary': t.get('summary')} for t in s.get('topics', [])],
            'decisions': [d.get('text') for d in s.get('decisions', [])],
            'questions_for_you': [q.get('text') for q in s.get('questions_for_you', [])],
            'message_count': len(payload['messages'])}
    return Outcome(_dump(data))


# ── Drafts and proposals ─────────────────────────────────────────────────────

AUDIENCE = {'public': 'Public', 'friends': 'Friends', 'private': 'Only me'}


def _links(text):
    return list(dict.fromkeys(_URL_RE.findall(text or '')))[:10]


def _post_target(user, args):
    """Validated post arguments and the preview card. Raises ToolError if not allowed right now."""
    text = args['text'].strip()
    if not text:
        raise ToolError('A post needs some text.')
    preview = {'action': 'post', 'text': text, 'audience': AUDIENCE[args.get('privacy') or 'public'],
               'group': None, 'links': _links(text)}
    group_id = args.get('group_id')
    if group_id:
        group = visibility.visible_groups(user).filter(pk=group_id).first()
        if group is None:
            raise ToolError(NOT_FOUND)
        if not group.memberships.filter(user=user).exists():
            raise ToolError('Join this group before posting in it.')
        preview['group'] = {'id': group.id, 'name': group.name}
        preview['audience'] = f'Members of {group.name}' if group.privacy != 'public' else f'{group.name} (public)'
    clean = {'text': text, 'group_id': group_id or None, 'privacy': args.get('privacy') or 'public'}
    return clean, preview


def _message_target(user, args):
    from chats.models import ChatMember
    from chats.services import can_send
    text = args['text'].strip()
    if not text:
        raise ToolError('A message needs some text.')
    preview = {'action': 'message', 'text': text, 'links': _links(text)}
    if args.get('to_user_id'):
        User = get_user_model()
        to = User.objects.filter(pk=args['to_user_id'], is_active=True).first()
        if to is None or to.id == user.id or visibility.is_blocked(user, to):
            raise ToolError(NOT_FOUND)
        if not visibility.can_message(user, to):
            raise ToolError(f'{to.username} is not accepting messages from you.')
        preview['to'] = [{'id': to.id, 'username': to.username, 'name': to.get_full_name() or to.username}]
        preview['room'] = None
        return {'to_user_id': to.id, 'room_id': None, 'text': text}, preview
    member = ChatMember.objects.select_related('room').filter(room_id=args['room_id'], user=user).first()
    if member is None:
        raise ToolError(NOT_FOUND)
    room = member.room
    if not can_send(room, user):
        raise ToolError('You can no longer message this person.')
    blocked = visibility.blocked_ids(user)
    others = [m.user for m in ChatMember.objects.filter(room=room).exclude(user=user).select_related('user')
              if m.user_id not in blocked]
    preview['to'] = [{'id': u.id, 'username': u.username, 'name': u.get_full_name() or u.username}
                     for u in others[:20]]
    preview['room'] = {'id': room.id, 'name': room.name or None}
    return {'to_user_id': None, 'room_id': room.id, 'text': text}, preview


def draft_post(ctx, args):
    _, preview = _post_target(ctx.user, args)
    return Outcome(_dump({'draft': preview, 'note': 'Draft only. Nothing was posted. Use create_post to propose it.'}))


def draft_message(ctx, args):
    _, preview = _message_target(ctx.user, args)
    return Outcome(_dump({'draft': preview,
                          'note': 'Draft only. Nothing was sent. Use send_message to propose sending it.'}))


def _propose(ctx, tool, clean, preview):
    if ctx.run is not None and ctx.call_id:
        existing = Proposal.objects.filter(run=ctx.run, call_id=ctx.call_id).first()
        if existing:  # a retried step: the proposal already exists
            return existing
    pending = Proposal.objects.filter(owner=ctx.user, status=Proposal.STATUS_PENDING,
                                      expires_at__gt=timezone.now()).count()
    if pending >= MAX_PENDING_PROPOSALS:
        raise ToolError('Too many proposals are waiting for approval. Ask the member to review them first.')
    return Proposal.objects.create(
        owner=ctx.user, run=ctx.run, token=ctx.token, source=ctx.source, call_id=ctx.call_id, tool=tool,
        arguments=clean, preview=preview, model=ctx.model[:60], prompt_version=ctx.prompt_version[:20])


def _proposal_outcome(proposal, what):
    return Outcome(_dump({'proposal_id': proposal.id, 'status': 'waiting_for_approval',
                          'note': f'Nothing has been {what} yet. The member must approve this in the Andromeda app.'}),
                   proposal=proposal)


def create_post(ctx, args):
    clean, preview = _post_target(ctx.user, args)
    return _proposal_outcome(_propose(ctx, 'create_post', clean, preview), 'posted')


def send_message(ctx, args):
    clean, preview = _message_target(ctx.user, args)
    return _proposal_outcome(_propose(ctx, 'send_message', clean, preview), 'sent')


# ── Commits (only from an approved proposal) ─────────────────────────────────

def commit_post(user, arguments):
    from groups.models import Group
    from posts.models import Post
    from posts.tasks import process_post, queue_new_post_event
    clean, _ = _post_target(user, arguments)  # permissions as they are now, not when proposed
    group = Group.objects.get(pk=clean['group_id']) if clean['group_id'] else None
    post = Post.objects.create(author=user, content=clean['text'], privacy=clean['privacy'], group=group)
    process_post(post, created=True)  # hashtags, mentions and moderation, as for any post
    queue_new_post_event(post)
    return 'post', post.id, {'post_id': post.id, 'url': f'/posts/{post.id}'}


def commit_message(user, arguments):
    from chats import services
    from chats.models import ChatMember, ChatRoom, Message
    from chats.tasks import notify_offline_members
    clean, _ = _message_target(user, arguments)
    if clean['room_id']:
        room = ChatRoom.objects.get(pk=clean['room_id'])
    else:
        room = ChatRoom.objects.filter(room_type=ChatRoom.TYPE_DIRECT, members=user).filter(
            members__id=clean['to_user_id']).first()
        if room is None:
            room = ChatRoom.objects.create(room_type=ChatRoom.TYPE_DIRECT, created_by=user)
            ChatMember.objects.create(room=room, user=user, role=ChatMember.ROLE_ADMIN)
            ChatMember.objects.create(room=room, user_id=clean['to_user_id'])
    msg = Message.objects.create(room=room, sender=user, content=clean['text'])
    ChatRoom.objects.filter(pk=room.pk).update(updated_at=timezone.now())

    def after_commit():
        services.broadcast(room.id, {'type': 'chat_message',
                                     'message': services.payload(services.message_queryset().get(pk=msg.pk))})
        try:
            notify_offline_members.apply_async(args=[msg.id, room.id, user.id], queue='messages')
        except Exception:  # noqa: S110 - the message is saved; a missed notification isn't fatal
            pass
    transaction.on_commit(after_commit)
    return 'message', msg.id, {'message_id': msg.id, 'room_id': room.id, 'url': f'/chat/{room.id}'}


# ── Registry ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type
    schema: dict
    run: object
    scope: str = PersonalAccessToken.SCOPE_READ
    commit: object = None

    @property
    def writes(self):
        return self.commit is not None


_MSG_PROPS = {'to_user_id': {**_INT, 'description': 'Send a direct message to this person (an id from find_people).'},
              'room_id': {**_INT, 'description': 'Or send to this existing chat (an id from list_my_chats).'},
              'text': _TEXT}
_POST_PROPS = {'text': _TEXT, 'group_id': {**_INT, 'description': 'Post in this group (from list_my_groups).'},
               'privacy': {'type': 'string', 'enum': ['public', 'friends', 'private'],
                           'description': 'Who can see a timeline post. Defaults to public.'}}

TOOLS = {t.name: t for t in [
    Tool('search_content', 'Search posts, listings, groups, pages and videos the member can see. Returns ids, '
         'titles and short excerpts.', SearchArgs,
         _obj({'query': {**_STR, 'description': 'What to look for.'},
               'types': {'type': 'array', 'items': {'type': 'string', 'enum': KINDS},
                         'description': 'Limit to these content types.'}}, ['query']), search_content),
    Tool('get_post', 'Read one post the member can see, by its number (posts:12 is 12).', IdArgs,
         _obj({'id': _INT}, ['id']), get_post),
    Tool('list_my_groups', "List the groups the member belongs to, with their ids.", NoArgs, _obj({}), list_my_groups),
    Tool('list_my_chats', "List the member's chats, with their ids and who is in them.", NoArgs, _obj({}),
         list_my_chats),
    Tool('find_people', 'Find people by name or username, with their ids and whether the member can message them.',
         PeopleArgs, _obj({'query': _STR}, ['query']), find_people),
    Tool('search_listings', 'Search marketplace listings the member can see, optionally under a price or near '
         "the member's city.", ListingArgs,
         _obj({'query': _STR, 'max_price': {'type': 'number', 'minimum': 0},
               'near_me': {'type': 'boolean', 'description': "Within 50 km of the member's profile city."}}),
         search_listings),
    Tool('summarise_thread', 'Summarise a chat the member is in: topics, decisions and questions for them.',
         RoomArgs, _obj({'room_id': _INT}, ['room_id']), summarise_thread),
    Tool('draft_post', 'Check and preview a post without publishing anything.', PostArgs,
         _obj(_POST_PROPS, ['text']), draft_post),
    Tool('draft_message', 'Check and preview a direct message without sending anything.', MessageArgs,
         _obj(_MSG_PROPS, ['text']), draft_message),
    Tool('create_post', 'Propose publishing a post as the member. Nothing is published until the member approves '
         'the proposal in the Andromeda app.', PostArgs, _obj(_POST_PROPS, ['text']), create_post,
         scope=PersonalAccessToken.SCOPE_PROPOSE, commit=commit_post),
    Tool('send_message', 'Propose sending a message as the member. Nothing is sent until the member approves the '
         'proposal in the Andromeda app.', MessageArgs, _obj(_MSG_PROPS, ['text']), send_message,
         scope=PersonalAccessToken.SCOPE_PROPOSE, commit=commit_message),
]}


def specs(scopes=None):
    """Tool definitions for the model (or an MCP client), limited to the given scopes."""
    return [{'name': t.name, 'description': t.description, 'input_schema': t.schema}
            for t in TOOLS.values() if scopes is None or t.scope in scopes]


def execute(name, raw_args, ctx):
    """Run one tool call as ``ctx.user``. Never raises for the model's mistakes: errors are outcomes."""
    tool = TOOLS.get(name)
    if tool is None:
        return Outcome(f'Unknown tool "{str(name)[:40]}".', is_error=True)
    if ctx.scopes is not None and tool.scope not in ctx.scopes:
        return Outcome(f'This access token does not have the "{tool.scope}" scope.', is_error=True)
    parsed = tool.args(data=raw_args if raw_args is not None else {})
    if not parsed.is_valid():
        return Outcome(_errors(parsed.errors)[:500], is_error=True)
    try:
        return tool.run(ctx, dict(parsed.validated_data))
    except ToolError as exc:
        return Outcome(str(exc)[:500], is_error=True)


def commit(proposal, user):
    """Perform an approved proposal's write. Raises ToolError if it's no longer allowed."""
    tool = TOOLS.get(proposal.tool)
    if tool is None or not tool.writes:
        raise ToolError('This proposal can no longer be carried out.')
    parsed = tool.args(data=proposal.arguments)
    if not parsed.is_valid():
        raise ToolError('This proposal can no longer be carried out.')
    return tool.commit(user, dict(parsed.validated_data))
