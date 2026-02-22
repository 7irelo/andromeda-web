from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import FriendRequest, Follow, Block
from .serializers import (
    UserSerializer, RegisterSerializer,
    AndromedaTokenSerializer, FriendRequestSerializer,
)

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UserSerializer(user, context={'request': request}).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }, status=status.HTTP_201_CREATED)


class LoginView(TokenObtainPairView):
    serializer_class = AndromedaTokenSerializer
    permission_classes = [permissions.AllowAny]


class MeView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        refresh_token = request.data.get('refresh')
        if refresh_token:
            try:
                from rest_framework_simplejwt.tokens import RefreshToken as RT
                token = RT(refresh_token)
                token.blacklist()
            except Exception:
                pass
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UserSerializer
    queryset = User.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(username__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )
        return qs

    def get_object(self):
        # Allow lookup by username or pk
        lookup = self.kwargs.get('pk')
        if lookup and not lookup.isdigit():
            return get_object_or_404(User, username=lookup)
        return super().get_object()

    @action(detail=False, methods=['get'])
    def suggestions(self, request):
        """Friend / follow suggestions via Neo4j graph."""
        try:
            from users.graph_models import UserNode
            node = UserNode.nodes.get_or_none(user_id=request.user.id)
            if node:
                recs = node.get_friend_recommendations()
                user_ids = [r['user_id'] for r in recs]
                users = User.objects.filter(id__in=user_ids)
                return Response(UserSerializer(users, many=True, context={'request': request}).data)
        except Exception:
            pass
        # Fallback: users not yet followed / friended
        blocked = Block.objects.filter(blocker=request.user).values_list('blocked_id', flat=True)
        following = Follow.objects.filter(follower=request.user).values_list('following_id', flat=True)
        # Exclude anyone already involved in a friend request with the current user
        involved = FriendRequest.objects.filter(
            Q(sender=request.user) | Q(receiver=request.user)
        )
        involved_ids = (
            list(involved.values_list('sender_id', flat=True)) +
            list(involved.values_list('receiver_id', flat=True))
        )
        exclude_ids = set(list(following) + list(blocked) + involved_ids + [request.user.id])
        users = User.objects.exclude(id__in=exclude_ids).order_by('?')[:10]
        return Response(UserSerializer(users, many=True, context={'request': request}).data)


class FriendRequestViewSet(viewsets.ModelViewSet):
    serializer_class = FriendRequestSerializer

    def get_queryset(self):
        return FriendRequest.objects.filter(
            Q(sender=self.request.user) | Q(receiver=self.request.user)
        ).select_related('sender', 'receiver')

    def perform_create(self, serializer):
        receiver_id = self.request.data.get('receiver_id')
        receiver = get_object_or_404(User, id=receiver_id)
        if receiver == self.request.user:
            raise ValidationError({'detail': 'You cannot send a friend request to yourself.'})
        try:
            fr = serializer.save(sender=self.request.user, receiver=receiver)
        except IntegrityError:
            raise ValidationError({'detail': 'Friend request already sent.'})
        from notifications.tasks import send_friend_request_notification
        send_friend_request_notification.delay(
            self.request.user.id, receiver.id, fr.id
        )

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        fr = get_object_or_404(FriendRequest, pk=pk, receiver=request.user, status='pending')
        fr.status = FriendRequest.STATUS_ACCEPTED
        fr.save()
        # Create bidirectional follows
        Follow.objects.get_or_create(follower=fr.sender, following=fr.receiver)
        Follow.objects.get_or_create(follower=fr.receiver, following=fr.sender)
        return Response({'status': 'accepted'})

    @action(detail=True, methods=['post'])
    def decline(self, request, pk=None):
        fr = get_object_or_404(FriendRequest, pk=pk, receiver=request.user, status='pending')
        fr.status = FriendRequest.STATUS_DECLINED
        fr.save()
        return Response({'status': 'declined'})


class FollowView(generics.GenericAPIView):
    def post(self, request, user_id):
        target = get_object_or_404(User, id=user_id)
        if target == request.user:
            return Response({'error': 'Cannot follow yourself.'}, status=400)
        _, created = Follow.objects.get_or_create(follower=request.user, following=target)
        if created:
            from notifications.tasks import send_follow_notification
            send_follow_notification.delay(request.user.id, target.id)
        return Response({'following': True, 'created': created})

    def delete(self, request, user_id):
        target = get_object_or_404(User, id=user_id)
        Follow.objects.filter(follower=request.user, following=target).delete()
        return Response({'following': False})
