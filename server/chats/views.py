from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import ChatRoom, ChatMember, Message
from .serializers import ChatRoomSerializer, MessageSerializer

User = get_user_model()


class ChatRoomViewSet(viewsets.ModelViewSet):
    serializer_class = ChatRoomSerializer

    def get_queryset(self):
        return ChatRoom.objects.filter(
            members=self.request.user
        ).prefetch_related('chatmember_set__user').order_by('-updated_at')

    def create(self, request, *args, **kwargs):
        member_ids = request.data.get('member_ids', [])
        room_type = request.data.get('room_type', ChatRoom.TYPE_DIRECT)

        # For DMs: check if room already exists
        if room_type == ChatRoom.TYPE_DIRECT and len(member_ids) == 1:
            other_id = member_ids[0]
            existing = ChatRoom.objects.filter(
                room_type=ChatRoom.TYPE_DIRECT,
                members=request.user
            ).filter(members__id=other_id).first()
            if existing:
                return Response(ChatRoomSerializer(existing, context={'request': request}).data)

        room = ChatRoom.objects.create(
            room_type=room_type,
            name=request.data.get('name', ''),
            created_by=request.user,
        )
        # Add creator as admin
        ChatMember.objects.create(room=room, user=request.user, role=ChatMember.ROLE_ADMIN)
        # Add other members
        for uid in member_ids:
            user = get_object_or_404(User, id=uid)
            ChatMember.objects.get_or_create(room=room, user=user)

        return Response(ChatRoomSerializer(room, context={'request': request}).data, status=201)

    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        room = self.get_object()
        msgs = room.messages.filter(is_deleted=False).select_related(
            'sender', 'reply_to__sender'
        ).order_by('-created_at')

        page = self.paginate_queryset(msgs)
        if page is not None:
            return self.get_paginated_response(
                MessageSerializer(page, many=True, context={'request': request}).data
            )
        return Response(MessageSerializer(msgs, many=True, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        from django.utils import timezone
        room = self.get_object()
        ChatMember.objects.filter(room=room, user=request.user).update(last_read_at=timezone.now())
        return Response({'status': 'marked_read'})

    @action(detail=True, methods=['post'])
    def add_member(self, request, pk=None):
        room = self.get_object()
        user = get_object_or_404(User, id=request.data['user_id'])
        ChatMember.objects.get_or_create(room=room, user=user)
        return Response({'status': 'added'})


class MessageViewSet(viewsets.ModelViewSet):
    serializer_class = MessageSerializer

    def get_queryset(self):
        room_id = self.kwargs.get('room_pk') or self.request.query_params.get('room')
        qs = Message.objects.filter(is_deleted=False).select_related('sender')
        if room_id:
            qs = qs.filter(room_id=room_id)
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(sender=self.request.user)

    def perform_update(self, serializer):
        serializer.save(is_edited=True)

    def destroy(self, request, *args, **kwargs):
        msg = self.get_object()
        if msg.sender != request.user:
            return Response(status=403)
        msg.is_deleted = True
        msg.save()
        return Response(status=204)
