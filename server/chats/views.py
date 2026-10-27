import mimetypes

from django.contrib.auth import get_user_model
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from core import visibility
from core.validators import validate_attachment
from .models import ChatMember, ChatRoom, Message
from .serializers import ChatRoomSerializer, MessageSerializer

User = get_user_model()
MAX_GROUP_MEMBERS = 250


def _require_admin(room, user):
    if not ChatMember.objects.filter(room=room, user=user, role=ChatMember.ROLE_ADMIN).exists():
        raise PermissionDenied('Only room admins can do that.')


def _addable_user(adder, user_id):
    user = get_object_or_404(User, id=user_id, is_active=True)
    if user.id != adder.id and not visibility.can_message(adder, user):
        raise PermissionDenied(f'{user.username} is not accepting messages from you.')
    return user


class ChatRoomViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Rooms are created through ``create`` and managed through explicit actions only."""

    serializer_class = ChatRoomSerializer

    def get_queryset(self):
        return ChatRoom.objects.filter(
            members=self.request.user
        ).prefetch_related('chatmember_set__user').order_by('-updated_at')

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
                return Response(ChatRoomSerializer(existing, context={'request': request}).data)

        room = ChatRoom.objects.create(
            room_type=room_type,
            name=str(request.data.get('name', ''))[:255] if room_type == ChatRoom.TYPE_GROUP else '',
            created_by=request.user,
        )
        ChatMember.objects.create(room=room, user=request.user, role=ChatMember.ROLE_ADMIN)
        ChatMember.objects.bulk_create([ChatMember(room=room, user=u) for u in members])
        return Response(ChatRoomSerializer(room, context={'request': request}).data, status=201)

    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        room = self.get_object()
        msgs = room.messages.filter(is_deleted=False).select_related(
            'sender', 'reply_to__sender'
        ).order_by('-created_at')
        page = self.paginate_queryset(msgs)
        return self.get_paginated_response(
            MessageSerializer(page, many=True, context={'request': request}).data
        )

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
        if room.chatmember_set.count() >= MAX_GROUP_MEMBERS:
            raise ValidationError({'detail': 'This group chat is full.'})
        user = _addable_user(request.user, request.data.get('user_id'))
        ChatMember.objects.get_or_create(room=room, user=user)
        return Response({'status': 'added'})

    @action(detail=True, methods=['post'])
    def remove_member(self, request, pk=None):
        room = self.get_object()
        _require_admin(room, request.user)
        ChatMember.objects.filter(room=room, user_id=request.data.get('user_id')).exclude(
            user=request.user
        ).delete()
        return Response({'status': 'removed'})

    @action(detail=True, methods=['post'])
    def leave(self, request, pk=None):
        room = self.get_object()
        ChatMember.objects.filter(room=room, user=request.user).delete()
        if not room.chatmember_set.exists():
            room.delete()
        elif not room.chatmember_set.filter(role=ChatMember.ROLE_ADMIN).exists():
            # Hand admin to the longest-standing member so the room stays manageable.
            successor = room.chatmember_set.order_by('joined_at').first()
            successor.role = ChatMember.ROLE_ADMIN
            successor.save(update_fields=['role'])
        return Response({'status': 'left'})

    @action(detail=True, methods=['patch'])
    def rename(self, request, pk=None):
        room = self.get_object()
        if room.room_type != ChatRoom.TYPE_GROUP:
            raise ValidationError({'detail': 'Only group chats have names.'})
        _require_admin(room, request.user)
        room.name = str(request.data.get('name', ''))[:255]
        room.save(update_fields=['name', 'updated_at'])
        return Response(ChatRoomSerializer(room, context={'request': request}).data)


class MessageViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                     mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Messages are only ever visible inside rooms the user belongs to."""

    serializer_class = MessageSerializer
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        return Message.objects.filter(
            room__members=self.request.user, is_deleted=False
        ).select_related('sender', 'room')

    def perform_create(self, serializer):
        room = serializer.validated_data['room']
        if not ChatMember.objects.filter(room=room, user=self.request.user).exists():
            raise PermissionDenied('You are not a member of this room.')
        if room.room_type == ChatRoom.TYPE_DIRECT:
            other = room.members.exclude(id=self.request.user.id).first()
            if other and not visibility.can_message(self.request.user, other):
                raise PermissionDenied('You can no longer message this person.')
        upload = self.request.FILES.get('file')
        if upload:
            validate_attachment(upload)
        reply_to = serializer.validated_data.get('reply_to')
        if reply_to and reply_to.room_id != room.id:
            raise ValidationError({'reply_to': 'You can only reply to messages in the same room.'})
        serializer.save(sender=self.request.user)
        ChatRoom.objects.filter(pk=room.pk).update(updated_at=timezone.now())

    def perform_update(self, serializer):
        if serializer.instance.sender_id != self.request.user.id:
            raise PermissionDenied('You can only edit your own messages.')
        serializer.save(is_edited=True)

    def destroy(self, request, *args, **kwargs):
        msg = self.get_object()
        if msg.sender_id != request.user.id:
            raise PermissionDenied('You can only delete your own messages.')
        msg.is_deleted = True
        msg.content = ''
        msg.save(update_fields=['is_deleted', 'content', 'updated_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'])
    def file(self, request, pk=None):
        """Stream an attachment after the membership check in get_queryset()."""
        msg = self.get_object()
        if not msg.file:
            raise ValidationError({'detail': 'This message has no attachment.'})
        content_type = mimetypes.guess_type(msg.file.name)[0] or 'application/octet-stream'
        response = FileResponse(msg.file.open('rb'), content_type=content_type, as_attachment=True)
        response['X-Content-Type-Options'] = 'nosniff'
        response['Content-Security-Policy'] = "default-src 'none'; sandbox"
        response['Cache-Control'] = 'private, no-store'
        return response
