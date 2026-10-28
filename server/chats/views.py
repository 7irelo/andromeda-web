import mimetypes
import os
from datetime import datetime, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection, transaction
from django.db.models import Count, DateTimeField, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from core import ai_client, visibility
from core.validators import sanitize_image, validate_attachment
from . import services
from .audio import MIMETYPE_BY_EXT, validate_voice
from .models import ChatMember, ChatRoom, Message
from .serializers import ChatRoomSerializer, MessageSerializer

User = get_user_model()
MAX_GROUP_MEMBERS = 250
CATCH_UP_MAX_MESSAGES = 300
AFTER_ID_LIMIT = 200
SEARCH_MIN_CHARS = 2
SEARCH_MAX_CHARS = 100
SEARCH_LIMIT = 50
EPOCH = datetime(1970, 1, 1, tzinfo=dt_timezone.utc)


def _require_admin(room, user):
    if not ChatMember.objects.filter(room=room, user=user, role=ChatMember.ROLE_ADMIN).exists():
        raise PermissionDenied('Only room admins can do that.')


def _require_group(room):
    if room.room_type != ChatRoom.TYPE_GROUP:
        raise ValidationError({'detail': 'Only group chats can be managed.'})


def _addable_user(adder, user_id):
    if not str(user_id).isdigit():
        raise ValidationError({'user_id': 'Provide a user id.'})
    user = get_object_or_404(User, id=user_id, is_active=True)
    if user.id != adder.id and not visibility.can_message(adder, user):
        raise PermissionDenied(f'{user.username} is not accepting messages from you.')
    return user


def _member_of(room, user_id):
    if not str(user_id).isdigit():
        raise ValidationError({'user_id': 'Provide a user id.'})
    return get_object_or_404(ChatMember, room=room, user_id=int(user_id))


def _ensure_admin(room):
    """Every group keeps at least one admin: promote the longest-standing member if needed."""
    if not room.chatmember_set.filter(role=ChatMember.ROLE_ADMIN).exists():
        successor = room.chatmember_set.order_by('joined_at', 'id').first()
        if successor:
            successor.role = ChatMember.ROLE_ADMIN
            successor.save(update_fields=['role'])


def _room_changed(room):
    services.broadcast_on_commit(room.id, {'type': 'room_updated'})


def rooms_for(user):
    """The user's rooms with their unread count and latest message id, in one query."""
    last_read = ChatMember.objects.filter(room=OuterRef('pk'), user=user).values('last_read_at')[:1]
    unread = (
        Message.objects.filter(room=OuterRef('pk'), is_deleted=False, created_at__gt=OuterRef('_last_read'))
        .exclude(sender_id=user.id).order_by().values('room').annotate(n=Count('id')).values('n')
    )
    latest = Message.objects.filter(room=OuterRef('pk'), is_deleted=False).order_by('-created_at', '-id')
    return (
        ChatRoom.objects.filter(members=user)
        .annotate(_last_read=Coalesce(Subquery(last_read), Value(EPOCH), output_field=DateTimeField()))
        .annotate(
            _unread=Coalesce(Subquery(unread, output_field=IntegerField()), 0),
            _last_message_id=Subquery(latest.values('id')[:1]),
        )
        .prefetch_related('chatmember_set__user')
        .order_by('-updated_at')
    )


def _message_list(qs):
    return services.message_queryset().filter(pk__in=qs.values('pk')).annotate(read_count=Count('reads'))


def _search(qs, query):
    """Postgres full-text over text and transcripts, substring match elsewhere (SQLite tests)."""
    substring = Q(content__icontains=query) | Q(transcript__icontains=query)
    if connection.vendor == 'postgresql':
        from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
        vector = SearchVector('content', 'transcript')
        search = SearchQuery(query, search_type='websearch')
        # Filter on a real match (@@), not on rank: ts_rank is never exactly 0.
        return qs.annotate(_doc=vector, _rank=SearchRank(vector, search)).filter(
            Q(_doc=search) | substring
        ).order_by('-_rank', '-created_at')
    return qs.filter(substring).order_by('-created_at')


class ChatRoomViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Rooms are created through ``create`` and managed through explicit actions only."""

    serializer_class = ChatRoomSerializer
    throttle_scope = 'ai'  # only used by catch_up, which opts into ScopedRateThrottle

    def get_queryset(self):
        return rooms_for(self.request.user)

    def get_serializer_context(self):
        return {**super().get_serializer_context(), 'last_messages': getattr(self, '_last_messages', None)}

    def _load_last_messages(self, rooms):
        ids = [r._last_message_id for r in rooms if getattr(r, '_last_message_id', None)]
        self._last_messages = {m.id: m for m in Message.objects.filter(id__in=ids).select_related('sender')}

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        self._load_last_messages(page)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    def retrieve(self, request, *args, **kwargs):
        room = self.get_object()
        self._load_last_messages([room])
        return Response(self.get_serializer(room).data)

    def _room_response(self, room, status_code=200):
        return Response(ChatRoomSerializer(room, context={'request': self.request}).data, status=status_code)

    def create(self, request, *args, **kwargs):
        member_ids = request.data.get('member_ids', [])
        if not isinstance(member_ids, list) or not all(str(i).isdigit() for i in member_ids):
            raise ValidationError({'member_ids': 'Provide a list of user ids.'})
        member_ids = list({int(i) for i in member_ids} - {request.user.id})
        room_type = request.data.get('room_type', ChatRoom.TYPE_DIRECT)
        if room_type not in (ChatRoom.TYPE_DIRECT, ChatRoom.TYPE_GROUP):
            raise ValidationError({'room_type': 'Invalid room type.'})
        if room_type == ChatRoom.TYPE_DIRECT and len(member_ids) != 1:
            raise ValidationError({'member_ids': 'A direct message needs exactly one other person.'})
        if not member_ids or len(member_ids) >= MAX_GROUP_MEMBERS:
            raise ValidationError({'member_ids': f'Add between 1 and {MAX_GROUP_MEMBERS - 1} people.'})

        members = [_addable_user(request.user, uid) for uid in member_ids]

        if room_type == ChatRoom.TYPE_DIRECT:
            existing = ChatRoom.objects.filter(
                room_type=ChatRoom.TYPE_DIRECT, members=request.user
            ).filter(members=members[0]).first()
            if existing:
                return self._room_response(existing)

        room = ChatRoom.objects.create(
            room_type=room_type,
            name=str(request.data.get('name', ''))[:255] if room_type == ChatRoom.TYPE_GROUP else '',
            created_by=request.user,
        )
        ChatMember.objects.create(room=room, user=request.user, role=ChatMember.ROLE_ADMIN)
        ChatMember.objects.bulk_create([ChatMember(room=room, user=u) for u in members])
        return self._room_response(room, status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def unread(self, request):
        """Unread counts for every room plus the totals for the global badge."""
        counts = {room_id: n for room_id, n in rooms_for(request.user).values_list('id', '_unread') if n}
        return Response({'total': sum(counts.values()), 'rooms_with_unread': len(counts), 'rooms': counts})

    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        """
        Newest first, paginated. Deleted messages come back as tombstones.
        ``?after_id=<id>`` returns up to 200 newer messages oldest first, for
        reconnect catch-up.
        """
        room = self.get_object()
        msgs = room.messages.all()
        after_id = request.query_params.get('after_id')
        if after_id is not None:
            if not after_id.isdigit():
                raise ValidationError({'after_id': 'Must be a message id.'})
            newer = list(_message_list(msgs.filter(id__gt=int(after_id))).order_by('id')[:AFTER_ID_LIMIT + 1])
            return Response({
                'results': MessageSerializer(newer[:AFTER_ID_LIMIT], many=True, context={'request': request}).data,
                'has_more': len(newer) > AFTER_ID_LIMIT,
            })
        page = self.paginate_queryset(_message_list(msgs).order_by('-created_at', '-id'))
        return self.get_paginated_response(
            MessageSerializer(page, many=True, context={'request': request}).data
        )

    @action(detail=True, methods=['get'])
    def search(self, request, pk=None):
        """Search this room's messages and voice-note transcripts. Members only (get_object)."""
        room = self.get_object()
        query = str(request.query_params.get('q', '')).strip()
        if not SEARCH_MIN_CHARS <= len(query) <= SEARCH_MAX_CHARS:
            raise ValidationError({'q': f'Search for {SEARCH_MIN_CHARS} to {SEARCH_MAX_CHARS} characters.'})
        qs = room.messages.filter(is_deleted=False).exclude(sender_id__in=visibility.blocked_ids(request.user))
        ids = list(_search(qs, query).values_list('id', flat=True)[:SEARCH_LIMIT])
        found = {m.id: m for m in _message_list(Message.objects.filter(id__in=ids))}
        results = [found[i] for i in ids if i in found]
        return Response({
            'query': query,
            'results': MessageSerializer(results, many=True, context={'request': request}).data,
        })

    @action(detail=True, methods=['get'])
    def presence(self, request, pk=None):
        room = self.get_object()
        return Response({'online': services.visible_online_ids(request.user, room.id)})

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        room = self.get_object()
        ChatMember.objects.filter(room=room, user=request.user).update(last_read_at=timezone.now())
        return Response({'status': 'marked_read'})

    @action(detail=True, methods=['post'])
    def add_member(self, request, pk=None):
        room = self.get_object()
        if room.room_type != ChatRoom.TYPE_GROUP:
            raise ValidationError({'detail': 'Members can only be added to group chats.'})
        _require_admin(room, request.user)
        if ChatMember.objects.filter(room=room).count() >= MAX_GROUP_MEMBERS:
            raise ValidationError({'detail': 'This group chat is full.'})
        user = _addable_user(request.user, request.data.get('user_id'))
        ChatMember.objects.get_or_create(room=room, user=user)
        _room_changed(room)
        return Response({'status': 'added'})

    @action(detail=True, methods=['post'])
    def remove_member(self, request, pk=None):
        room = self.get_object()
        _require_group(room)
        _require_admin(room, request.user)
        member = _member_of(room, request.data.get('user_id'))
        if member.user_id == request.user.id:
            raise ValidationError({'detail': 'Use leave to remove yourself.'})
        member.delete()
        transaction.on_commit(lambda: services.kick(room.id, member.user_id))
        _room_changed(room)
        return Response({'status': 'removed'})

    @action(detail=True, methods=['post'])
    def set_role(self, request, pk=None):
        room = self.get_object()
        _require_group(room)
        _require_admin(room, request.user)
        role = request.data.get('role')
        if role not in (ChatMember.ROLE_ADMIN, ChatMember.ROLE_MEMBER):
            raise ValidationError({'role': 'Role must be admin or member.'})
        with transaction.atomic():
            member = _member_of(room, request.data.get('user_id'))
            if role == ChatMember.ROLE_MEMBER and member.role == ChatMember.ROLE_ADMIN and not (
                    room.chatmember_set.filter(role=ChatMember.ROLE_ADMIN).exclude(pk=member.pk).exists()):
                raise ValidationError({'detail': 'A group needs at least one admin.'})
            member.role = role
            member.save(update_fields=['role'])
        _room_changed(room)
        return Response({'status': 'updated', 'user_id': member.user_id, 'role': role})

    @action(detail=True, methods=['post'])
    def leave(self, request, pk=None):
        room = self.get_object()
        with transaction.atomic():
            ChatMember.objects.filter(room=room, user=request.user).delete()
            if not ChatMember.objects.filter(room=room).exists():
                room.delete()
                return Response({'status': 'left'})
            # Hand admin to the longest-standing member so the room stays manageable.
            _ensure_admin(room)
        transaction.on_commit(lambda: services.kick(room.id, request.user.id))
        _room_changed(room)
        return Response({'status': 'left'})

    @action(detail=True, methods=['patch', 'post'])
    def rename(self, request, pk=None):
        room = self.get_object()
        if room.room_type != ChatRoom.TYPE_GROUP:
            raise ValidationError({'detail': 'Only group chats have names.'})
        _require_admin(room, request.user)
        name = str(request.data.get('name', '')).strip()
        if not name or len(name) > 255:
            raise ValidationError({'name': 'Give the group a name of up to 255 characters.'})
        room.name = name
        room.save(update_fields=['name', 'updated_at'])
        _room_changed(room)
        return self._room_response(room)

    @action(detail=True, methods=['post', 'delete'], parser_classes=[MultiPartParser, FormParser])
    def avatar(self, request, pk=None):
        """Upload (multipart ``avatar``) or remove the group picture. Admins only."""
        room = self.get_object()
        _require_group(room)
        _require_admin(room, request.user)
        if room.avatar:
            room.avatar.delete(save=False)
        if request.method == 'DELETE':
            room.avatar = None
        else:
            upload = request.FILES.get('avatar')
            if not upload:
                raise ValidationError({'avatar': 'Choose an image.'})
            try:
                room.avatar = sanitize_image(upload)
            except DjangoValidationError as exc:
                raise ValidationError({'avatar': exc.messages})
        room.save(update_fields=['avatar', 'updated_at'])
        _room_changed(room)
        return self._room_response(room)

    @action(detail=True, methods=['post'], throttle_classes=[ScopedRateThrottle])
    def catch_up(self, request, pk=None):
        """AI summary of what the user missed. Membership is enforced by get_object()."""
        room = self.get_object()
        if request.user.ai_opt_out:
            return Response({'detail': 'You have turned off AI features in your settings.'},
                            status=status.HTTP_403_FORBIDDEN)
        member = ChatMember.objects.get(room=room, user=request.user)
        # Members who turned AI off never have their messages sent to a model.
        msgs = room.messages.filter(is_deleted=False).exclude(
            sender_id__in=visibility.blocked_ids(request.user)
        ).exclude(sender__ai_opt_out=True).select_related('sender').order_by('-created_at')
        unread = msgs.filter(created_at__gt=member.last_read_at) if member.last_read_at else msgs
        batch = list(unread[:CATCH_UP_MAX_MESSAGES])
        if len(batch) < 3:
            # Nothing much unread (opening a room marks it read): recap the latest conversation instead.
            batch = list(msgs[:50])
        batch.reverse()
        payload = {
            'room_name': room.name,
            'viewer': request.user.username,
            'messages': [{'id': m.id, 'sender': m.sender.username if m.sender else 'deleted user',
                          'text': (m.content or m.transcript)[:2000], 'sent_at': m.created_at.isoformat()}
                         for m in batch if m.content or m.transcript],
        }
        try:
            result = ai_client.call('/v1/catchup', payload, user_id=request.user.id)
        except ai_client.AIRejected as exc:
            return Response({'detail': exc.detail}, status=exc.status)
        except ai_client.AIUnavailable:
            return Response({'detail': 'Summaries are unavailable right now.'}, status=503)
        return Response({**result['summary'], 'message_count': len(payload['messages'])})


class MessageViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                     mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Messages are only ever visible inside rooms the user belongs to."""

    serializer_class = MessageSerializer
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        return services.message_queryset().filter(room__members=self.request.user, is_deleted=False)

    def perform_create(self, serializer):
        room = serializer.validated_data['room']
        if not ChatMember.objects.filter(room=room, user=self.request.user).exists():
            raise PermissionDenied('You are not a member of this room.')
        if not services.can_send(room, self.request.user):
            raise PermissionDenied('You can no longer message this person.')
        reply_to = serializer.validated_data.get('reply_to')
        if reply_to and (reply_to.room_id != room.id or reply_to.is_deleted):
            raise ValidationError({'reply_to': 'You can only reply to messages in the same room.'})

        upload = self.request.FILES.get('file')
        message_type = serializer.validated_data.get('message_type', Message.TYPE_TEXT)
        extra = {}
        try:
            if message_type == Message.TYPE_VOICE:
                if not upload:
                    raise ValidationError({'file': 'Attach the recording.'})
                clean, _, duration = validate_voice(upload)
                extra = {
                    'file': clean, 'duration_s': duration, 'content': '',
                    'transcript_status': (Message.TRANSCRIPT_PENDING if ai_client.enabled()
                                          else Message.TRANSCRIPT_NONE),
                }
            elif upload:
                validate_attachment(upload)
            elif not serializer.validated_data.get('content', '').strip():
                raise ValidationError({'content': 'A message needs some text or an attachment.'})
        except DjangoValidationError as exc:
            raise ValidationError({'file': exc.messages})

        msg = serializer.save(sender=self.request.user, **extra)
        ChatRoom.objects.filter(pk=room.pk).update(updated_at=timezone.now())

        def after_commit():
            services.broadcast(room.id, {
                'type': 'chat_message', 'message': services.payload(services.message_queryset().get(pk=msg.pk)),
            })
            from .tasks import notify_offline_members, transcribe_voice_note
            notify_offline_members.apply_async(args=[msg.id, room.id, self.request.user.id], queue='messages')
            if msg.transcript_status == Message.TRANSCRIPT_PENDING:
                transcribe_voice_note.apply_async(args=[msg.id], queue='messages')
        transaction.on_commit(after_commit)

    def update(self, request, *args, **kwargs):
        msg = self.get_object()
        serializer = self.get_serializer(msg, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            msg = services.edit_message(request.user, msg.room_id, msg.id,
                                        serializer.validated_data.get('content', msg.content))
        except services.ChatActionError as exc:
            return Response({'detail': exc.detail}, status=exc.status)
        services.broadcast_on_commit(msg.room_id, {'type': 'message_updated', 'message': services.payload(msg)})
        return Response(MessageSerializer(msg, context={'request': request}).data)

    def destroy(self, request, *args, **kwargs):
        msg = self.get_object()
        try:
            msg = services.delete_message(request.user, msg.room_id, msg.id)
        except services.ChatActionError as exc:
            return Response({'detail': exc.detail}, status=exc.status)
        services.broadcast_on_commit(msg.room_id, {'type': 'message_updated', 'message': services.payload(msg)})
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'])
    def file(self, request, pk=None):
        """Stream an attachment after the membership check in get_queryset()."""
        msg = self.get_object()
        if not msg.file:
            raise ValidationError({'detail': 'This message has no attachment.'})
        ext = os.path.splitext(msg.file.name)[1].lower()
        if msg.message_type == Message.TYPE_VOICE and ext in MIMETYPE_BY_EXT:
            content_type = MIMETYPE_BY_EXT[ext]
        else:
            content_type = mimetypes.guess_type(msg.file.name)[0] or 'application/octet-stream'
        response = FileResponse(msg.file.open('rb'), content_type=content_type, as_attachment=True)
        response['X-Content-Type-Options'] = 'nosniff'
        response['Content-Security-Policy'] = "default-src 'none'; sandbox"
        response['Cache-Control'] = 'private, no-store'
        return response
